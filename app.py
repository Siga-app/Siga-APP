import os
# Garante que a pasta persistente exista no container.
os.makedirs("/app/instance", exist_ok=True)

from flask import Flask, render_template, request, redirect, url_for, flash, Response, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from apscheduler.schedulers.background import BackgroundScheduler
import re, urllib.parse, pytz
from datetime import datetime, timedelta, date
from sqlalchemy import func, extract
from io import BytesIO
from openpyxl import Workbook
from xhtml2pdf import pisa

app = Flask(__name__)
app.config.from_object('config.Config')

# Configuração do Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login_view'
login_manager.session_protection = "strong"

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Definindo o timezone de São Paulo
sp_tz = pytz.timezone('America/Sao_Paulo')

# Filtro para URL encoding (usado para links, ex: WhatsApp)
@app.template_filter('urlencode')
def urlencode_filter(s):
    if isinstance(s, str):
        return urllib.parse.quote_plus(s)
    return s

# MODELO DE SOLICITAÇÃO com relacionamento em cascata para mensagens
class Solicitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    parent_name = db.Column(db.String(100), nullable=False)
    child_name = db.Column(db.String(100), nullable=False)  # "Aluno"
    grade = db.Column(db.String(50), nullable=False)         # "Série - Turma"
    category = db.Column(db.String(50), nullable=False)
    subcategory = db.Column(db.String(50), nullable=True)
    # Único campo para a descrição (se origem for WhatsAPP, esse campo fica vazio e usamos whatsapp_message)
    description = db.Column(db.Text, nullable=False)
    whatsapp_message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='Pendente')    # "Pendente", "Respondida", "Finalizada"
    coordinator = db.Column(db.String(50), nullable=False, server_default='Jéssica')
    assigned_to = db.Column(db.String(100), nullable=True)
    origin = db.Column(db.String(50), nullable=False)         # "Pessoalmente", "Ligação" ou "WhatsAPP"
    telefone = db.Column(db.String(20), nullable=True)        # Telefone de Contato
    created_at = db.Column(db.DateTime, server_default=func.now())
    updated_at = db.Column(db.DateTime, server_default=func.now(), onupdate=func.now())
    created_by = db.Column(db.String(100), nullable=False, default="")
    # Relacionamento com Message com cascade delete
    messages = db.relationship('Message', backref='solicitation', cascade="all, delete-orphan", lazy=True)

# MODELO DE MENSAGEM
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    solicitation_id = db.Column(db.Integer, db.ForeignKey('solicitation.id'), nullable=False)
    sender = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=func.now())

# MODELO DE USUÁRIO (dados fixos)
class User(UserMixin):
    def __init__(self, username, name, password):
        self.id = username
        self.name = name
        self.password = password

USERS = {
    "jessicaventura": User("jessicaventura", "Jéssica Ventura", "jessica123"),
    "brunabeatriz": User("brunabeatriz", "Bruna Beatriz", "bruna123"),
    "flaviapinto": User("flaviapinto", "Flávia Pinto", "flavia123"),
    "martafarias": User("martafarias", "Marta Farias", "marta123"),
    "marlymachado": User("marlymachado", "Marly Machado", "marly123")
}

@login_manager.user_loader
def load_user(user_id):
    return USERS.get(user_id)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login_view():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = USERS.get(username)
        if user and user.password == password:
            login_user(user, remember=True)
            flash("Login realizado com sucesso!")
            return redirect(url_for('dashboard'))
        else:
            flash("Usuário ou senha incorretos.")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout_view():
    logout_user()
    flash("Você saiu do sistema.")
    return redirect(url_for('home'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password_view():
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        user = USERS.get(current_user.id)
        if user.password != old_password:
            flash("Senha antiga incorreta.")
        elif new_password != confirm_password:
            flash("Novas senhas não conferem.")
        else:
            user.password = new_password
            flash("Senha alterada com sucesso!")
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register_solicitation():
    if request.method == 'POST':
        parent_name = request.form['parent_name']
        child_name = request.form['child_name']
        series = request.form['series']
        turma = request.form['turma']
        grade = f"{series} - {turma}"
        
        category = request.form['category']
        subcategory = request.form.get('subcategory', '')
        origin = request.form['origem']
        # Se a origem for WhatsAPP, usa o campo whatsapp_message; caso contrário, usa o campo description.
        if origin == "WhatsAPP":
            description = ""
            whatsapp_message = request.form['whatsapp_message']
        else:
            description = request.form['description']
            whatsapp_message = ""
        
        coordinator = request.form['coordinator']
        telefone = request.form.get('telefone', '')

        # Validação do telefone: somente dígitos (10 ou 11 dígitos)
        if origin in ["Pessoalmente", "Ligação", "WhatsAPP"]:
            pattern = r'^\d{10,11}$'
            if not re.match(pattern, telefone):
                flash("Telefone inválido. Use somente os dígitos (10 ou 11 dígitos).")
                return render_template('register.html')
            telefone = "+55" + telefone

        possui_audio = request.form.get('possui_audio', 'off')
        if possui_audio == 'on':
            if origin == "WhatsAPP":
                whatsapp_message += "\n[Áudio disponível]"
            else:
                description += "\n[Áudio disponível]"

        solicitation = Solicitation(
            parent_name=parent_name,
            child_name=child_name,
            grade=grade,
            category=category,
            subcategory=subcategory,
            description=description,
            whatsapp_message=whatsapp_message,
            coordinator=coordinator,
            origin=origin,
            telefone=telefone,
            created_by=current_user.id
        )
        db.session.add(solicitation)
        db.session.commit()

        flash('Solicitação registrada com sucesso!')
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    filter_category = request.args.get('filter_category', '')
    filter_subcategory = request.args.get('filter_subcategory', '')
    filter_coordinator = request.args.get('filter_coordinator', '')
    filter_status = request.args.get('filter_status', '')
    filter_search = request.args.get('filter_search', '').strip()

    query = Solicitation.query
    if filter_category:
        query = query.filter_by(category=filter_category)
    if filter_subcategory:
        query = query.filter_by(subcategory=filter_subcategory)
    if filter_coordinator:
        query = query.filter_by(coordinator=filter_coordinator)
    if filter_status:
        query = query.filter_by(status=filter_status)
    if filter_search:
        query = query.filter(Solicitation.child_name.ilike(f"%{filter_search}%"))

    local_now = datetime.now(sp_tz)
    if request.args.get('today') == "1":
        query = query.filter(
            extract('year', Solicitation.created_at) == local_now.year,
            extract('month', Solicitation.created_at) == local_now.month,
            extract('day', Solicitation.created_at) == local_now.day
        )
    if request.args.get('month') == "1":
        query = query.filter(
            extract('year', Solicitation.created_at) == local_now.year,
            extract('month', Solicitation.created_at) == local_now.month
        )

    solicitations = query.order_by(Solicitation.id.desc()).all()

    current_time = datetime.now(sp_tz)
    for sol in solicitations:
        last_update = sol.updated_at if sol.updated_at else sol.created_at
        last_update_aware = pytz.utc.localize(last_update).astimezone(sp_tz)
        sol.urgent = (current_time - last_update_aware) > timedelta(hours=24)

    # Atualize as categorias: "DOENÇA" foi substituída por "SAÚDE"
    categories = ["RECLAMAÇÃO", "SUGESTÃO", "DÚVIDAS", "PEDIDOS", "SAÚDE"]
    subcategories = ["", "SAÍDA ANTECIPADA", "AUTORIZACAO DE SAÍDA", "PEDIDO PARA REUNIÃO"]
    coordinators = ["Jéssica", "Bruna", "Flávia"]
    statuses = ["Pendente", "Respondida", "Finalizada"]

    return render_template('dashboard.html',
                           solicitations=solicitations,
                           filter_category=filter_category,
                           filter_subcategory=filter_subcategory,
                           filter_coordinator=filter_coordinator,
                           filter_status=filter_status,
                           filter_search=filter_search,
                           categories=categories,
                           subcategories=subcategories,
                           coordinators=coordinators,
                           statuses=statuses)

@app.route('/solicitation/<int:id>', methods=['GET', 'POST'])
@login_required
def solicitation_detail(id):
    solicitation = Solicitation.query.get_or_404(id)
    statuses = ["Pendente", "Respondida", "Finalizada"]

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            new_message = Message(
                solicitation_id=solicitation.id,
                sender=current_user.id,
                content=content
            )
            db.session.add(new_message)
            db.session.commit()
            flash('Mensagem adicionada!')
        new_status = request.form.get('new_status')
        if new_status in statuses:
            solicitation.status = new_status
            flash('Status atualizado!')
        new_coordinator = request.form.get('new_coordinator')
        if new_coordinator and new_coordinator in ["Jéssica", "Bruna", "Flávia"]:
            solicitation.coordinator = new_coordinator
            flash('Coordenadora atualizada!')
        db.session.commit()
        return redirect(url_for('solicitation_detail', id=id))

    messages = solicitation.messages
    coord_message = None
    for m in reversed(messages):
        if m.sender in ["jessicaventura", "brunabeatriz", "flaviapinto"]:
            coord_message = m.content
            break

    return render_template('solicitation_detail.html',
                           solicitation=solicitation,
                           messages=messages,
                           statuses=statuses,
                           coord_message=coord_message)

@app.route('/solicitation/<int:id>/delete', methods=['POST'])
@login_required
def delete_solicitation(id):
    solicitation = Solicitation.query.get_or_404(id)
    db.session.delete(solicitation)
    db.session.commit()
    flash("Solicitação deletada com sucesso!")
    return redirect(url_for('dashboard'))

# ---------------- Relatório Excel ----------------
@app.route('/solicitation/<int:id>/report/xls')
@login_required
def report_xls(id):
    solicitation = Solicitation.query.get_or_404(id)
    if solicitation.status != "Finalizada":
        flash("Relatório só disponível para solicitações finalizadas.")
        return redirect(url_for('solicitation_detail', id=id))
    wb = Workbook()
    ws = wb.active
    ws.title = "Dados Solicitação"
    ws.append(["Campo", "Valor"])
    ws.append(["ID", solicitation.id])
    ws.append(["Nome do Responsável", solicitation.parent_name])
    ws.append(["Aluno", solicitation.child_name])
    ws.append(["Série/Turma", solicitation.grade])
    ws.append(["Categoria", solicitation.category])
    ws.append(["Subcategoria", solicitation.subcategory])
    if solicitation.origin == "WhatsAPP":
        ws.append(["Descrição", solicitation.whatsapp_message])
    else:
        ws.append(["Descrição", solicitation.description])
    ws.append(["Status", solicitation.status])
    ws.append(["Coordenadora", solicitation.coordinator])
    ws.append(["Origem", solicitation.origin])
    ws.append(["Telefone", solicitation.telefone])
    ws.append(["Criado em", solicitation.created_at.strftime("%d/%m/%Y %H:%M") if solicitation.created_at else ""])
    ws.append(["Atualizado em", solicitation.updated_at.strftime("%d/%m/%Y %H:%M") if solicitation.updated_at else ""])

    ws2 = wb.create_sheet(title="Histórico Mensagens")
    ws2.append(["Remetente", "Mensagem", "Data/Hora"])
    for m in solicitation.messages:
        ws2.append([m.sender, m.content, m.timestamp.strftime("%d/%m/%Y %H:%M") if m.timestamp else ""])
    
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    filename = f"{solicitation.child_name.strip().replace(' ', '_')}_{solicitation.grade.strip().replace(' ', '_')}.xlsx"
    return send_file(stream, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ---------------- Relatórios Diário e Mensal ----------------

@app.route('/reports/daily')
@login_required
def daily_report():
    local_now = datetime.now(sp_tz)
    total_today = Solicitation.query.filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month,
        extract('day', Solicitation.created_at) == local_now.day
    ).count()
    resolved_today = Solicitation.query.filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month,
        extract('day', Solicitation.created_at) == local_now.day,
        Solicitation.status=='Finalizada'
    ).count()
    pending_today = Solicitation.query.filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month,
        extract('day', Solicitation.created_at) == local_now.day,
        Solicitation.status!='Finalizada'
    ).count()
    avg_resolution = db.session.query(func.avg(func.julianday(Solicitation.updated_at) - func.julianday(Solicitation.created_at)))\
        .filter(Solicitation.status=='Finalizada').scalar() or 0

    dist_category = db.session.query(
        Solicitation.category,
        func.count(Solicitation.id)
    ).filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month,
        extract('day', Solicitation.created_at) == local_now.day
    ).group_by(Solicitation.category).all()

    return render_template("daily_report.html",
                           total_today=total_today,
                           resolved_today=resolved_today,
                           pending_today=pending_today,
                           avg_resolution=avg_resolution,
                           dist_category=dist_category)

@app.route('/reports/monthly')
@login_required
def monthly_report():
    local_now = datetime.now(sp_tz)
    total_month = Solicitation.query.filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month
    ).count()

    resolved_month = Solicitation.query.filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month,
        Solicitation.status=='Finalizada'
    ).count()

    pending_month = Solicitation.query.filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month,
        Solicitation.status!='Finalizada'
    ).count()

    avg_resolution_month = db.session.query(func.avg(func.julianday(Solicitation.updated_at) - func.julianday(Solicitation.created_at)))\
        .filter(Solicitation.status=='Finalizada').scalar() or 0

    dist_category = db.session.query(
        Solicitation.category,
        func.count(Solicitation.id)
    ).filter(
        extract('year', Solicitation.created_at) == local_now.year,
        extract('month', Solicitation.created_at) == local_now.month
    ).group_by(Solicitation.category).all()

    return render_template("monthly_report.html",
                           total_month=total_month,
                           resolved_month=resolved_month,
                           pending_month=pending_month,
                           avg_resolution_month=avg_resolution_month,
                           dist_category=dist_category)

@app.route('/reports/filter')
@login_required
def reports_filter():
    category = request.args.get('category')
    period = request.args.get('period')  # "daily" ou "monthly"
    if period == "daily":
        return redirect(url_for('dashboard', filter_category=category, today="1"))
    elif period == "monthly":
        return redirect(url_for('dashboard', filter_category=category, month="1"))
    else:
        return redirect(url_for('dashboard'))

def gerar_relatorio_diario():
    from datetime import date
    total = Solicitation.query.count()
    resolvidas = Solicitation.query.filter_by(status='Finalizada').count()
    pendentes = Solicitation.query.filter_by(status='Pendente').count()
    respondidas = Solicitation.query.filter_by(status='Respondida').count()
    print(f"Relatório {date.today()}: Total: {total}, Pendente: {pendentes}, Respondida: {respondidas}, Finalizada: {resolvidas}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=gerar_relatorio_diario, trigger='cron', hour=18)
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
