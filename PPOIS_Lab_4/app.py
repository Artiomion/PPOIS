import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


app = Flask(__name__)
app.secret_key = os.urandom(24)


scheduler = BackgroundScheduler(daemon=True)
scheduler.start()



app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:11aa19112005@localhost/it_company?charset=utf8mb4'
app.config['SQLALCHEMY_ECHO'] = True
db = SQLAlchemy(app)



class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    related_entity_type = db.Column(db.String(50))
    related_entity_id = db.Column(db.Integer)

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Company(db.Model):
    __tablename__ = 'company'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    market_cap = db.Column(db.Integer, nullable=False)
    staff = db.Column(db.Integer, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    owner = db.relationship('User', backref=db.backref('company', uselist=False))

    programmers = db.relationship('Programmer', backref='company_rel', lazy=True)
    customers = db.relationship('Customer', backref='company_rel', lazy=True)
    projects = db.relationship('Project', backref='company_rel', lazy=True)
    tech_supports = db.relationship('TechnicalSupport', backref='company_rel', lazy=True)


class Programmer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    salary = db.Column(db.Integer, nullable=False)
    sphere = db.Column(db.String(50), nullable=False)
    programming_language = db.Column(db.String(50))
    code_quality = db.Column(db.String(20))
    test_type = db.Column(db.String(50))
    level_of_automation = db.Column(db.String(20))
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact_details = db.Column(db.String(100), nullable=False)
    budget = db.Column(db.Integer, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship('Project', backref='customer', lazy=True)



class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    requirements_analyzed = db.Column(db.Boolean, default=False)
    code_developed = db.Column(db.Boolean, default=False)
    tested = db.Column(db.Boolean, default=False)
    deployed = db.Column(db.Boolean, default=False)
    users_trained = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    def analyze_requirements(self):
        """Анализ требований проекта"""
        if not self.requirements_analyzed:
            self.requirements_analyzed = True
            db.session.commit()

            notify_admins(
                f"Требования проекта '{self.project_name}' проанализированы",
                'project',
                self.id
            )
            return True
        return False

    def develop_code(self, programmer):
        """Разработка кода проекта"""
        if not self.requirements_analyzed:
            raise ValueError("Сначала нужно проанализировать требования!")

        if not self.code_developed:
            self.code_developed = True
            db.session.commit()

            notify_admins(
                f"Разработка кода для проекта '{self.project_name}' начата (ответственный: {programmer.name})",
                'project',
                self.id
            )
            return True
        return False

    def test_code(self):
        """Тестирование проекта"""
        if not self.code_developed:
            raise ValueError("Сначала нужно разработать код!")

        if not self.tested:
            has_testers = Programmer.query.filter_by(
                company_id=self.company_id,
                sphere='QA'
            ).count() > 0

            if not has_testers:
                raise ValueError("В вашей компании нет QA-специалистов!")

            self.tested = True
            db.session.commit()

            notify_admins(
                f"Проект '{self.project_name}' успешно протестирован",
                'project',
                self.id
            )
            return True
        return False

    def deploy_and_support(self, tech_support, duration):
        """Внедрение проекта и назначение техподдержки"""
        if not self.tested:
            raise ValueError("Сначала нужно протестировать проект!")

        if not tech_support.availability:
            raise ValueError("Выбранный отдел техподдержки сейчас занят!")

        try:
            duration = int(duration)
            if duration <= 0:
                raise ValueError("Продолжительность должна быть положительным числом")
        except ValueError:
            raise ValueError("Некорректное значение продолжительности")

        tech_support.availability = False
        self.deployed = True
        db.session.commit()

        notify_admins(
            f"Проект '{self.project_name}' взят в работу техподдержкой {tech_support.responsibility_area}",
            'project',
            self.id
        )

        scheduler.add_job(
            release_tech_support,
            trigger=IntervalTrigger(seconds=duration),
            args=[tech_support.id],
            id=f"tech_release_{tech_support.id}_{self.id}"
        )

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        time_str = f"{hours}ч {minutes}м" if hours else f"{minutes} минут"

        notify_admins(
            f"Техподдержка {tech_support.responsibility_area} будет занята ~{time_str} для проекта '{self.project_name}'",
            'tech_support',
            tech_support.id
        )

    def train_users(self):
        """Обучение пользователей"""
        if not self.deployed:
            raise ValueError("Сначала нужно внедрить проект!")

        if not self.users_trained:
            self.users_trained = True
            db.session.commit()

            notify_admins(
                f"Обучение пользователей для проекта '{self.project_name}' завершено",
                'project',
                self.id
            )

            # Финализируем проект
            self.notify_project_completion()
            return True
        return False

    def notify_project_completion(self):
        """Уведомление о завершении проекта"""
        completion_msg = (
            f"Проект '{self.project_name}' успешно завершён!\n"
            f"Клиент: {self.customer.contact_details}\n"
            f"Этапы: {'✓' if self.requirements_analyzed else '✗'} Анализ | "
            f"{'✓' if self.code_developed else '✗'} Разработка | "
            f"{'✓' if self.tested else '✗'} Тестирование | "
            f"{'✓' if self.deployed else '✗'} Внедрение | "
            f"{'✓' if self.users_trained else '✗'} Обучение"
        )

        notify_admins(completion_msg, 'project', self.id)

    def get_project_progress(self):
        """Получение прогресса проекта в процентах"""
        stages = [
            self.requirements_analyzed,
            self.code_developed,
            self.tested,
            self.deployed,
            self.users_trained
        ]
        completed = sum(1 for stage in stages if stage)
        return (completed * 100) // len(stages)


class TechnicalSupport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    responsibility_area = db.Column(db.String(100), nullable=False)
    tools_used = db.Column(db.String(200), nullable=False)
    availability = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Требуются права администратора', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


def log_activity(action):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            result = f(*args, **kwargs)
            if 'user_id' in session:
                log = ActivityLog(
                    user_id=session['user_id'],
                    action=action
                )
                db.session.add(log)
                db.session.commit()
            return result

        return decorated_function

    return decorator


def release_tech_support(tech_support_id):
    with app.app_context():
        tech_support = TechnicalSupport.query.get(tech_support_id)
        if tech_support:
            tech_support.availability = True
            db.session.commit()
            message = f"Техподдержка {tech_support.responsibility_area} теперь доступна"
            admins = User.query.filter_by(is_admin=True).all()
            for admin in admins:
                notification = Notification(
                    user_id=admin.id,
                    message=message
                )
                db.session.add(notification)
            db.session.commit()


def create_notification(user_id, message, entity_type=None, entity_id=None):
    """Создание нового уведомления"""
    notification = Notification(
        user_id=user_id,
        message=message,
        related_entity_type=entity_type,
        related_entity_id=entity_id
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def notify_admins(message, entity_type=None, entity_id=None):
    """Отправка уведомления всем администраторам"""
    admins = User.query.filter_by(is_admin=True).all()
    for admin in admins:
        create_notification(admin.id, message, entity_type, entity_id)



# Маршруты аутентификации
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Заполните все поля', 'error')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not username or not password:
            flash('Заполните все поля', 'error')
            return redirect(url_for('register'))

        if len(username) < 4 or len(username) > 20:
            flash('Имя пользователя должно быть от 4 до 20 символов', 'error')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Это имя пользователя уже занято', 'error')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация прошла успешно. Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# Основные маршруты
@app.route('/')
@login_required
def index():
    user = User.query.get(session['user_id'])
    company = user.company
    return render_template('index.html', company=company, user=user)


@app.route('/create_company', methods=['GET', 'POST'])
@login_required
@log_activity('Создание компании')
def create_company():
    user = User.query.get(session['user_id'])

    if user.company:
        flash('У вас уже есть компания', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        market_cap = request.form.get('market_cap', '0').strip()
        staff = request.form.get('staff', '0').strip()

        if not name or not market_cap or not staff:
            flash('Заполните все поля', 'error')
            return redirect(url_for('create_company'))

        try:
            market_cap = int(market_cap)
            staff = int(staff)

            if market_cap <= 0 or staff <= 0:
                raise ValueError

        except ValueError:
            flash('Капитализация и количество сотрудников должны быть положительными числами', 'error')
            return redirect(url_for('create_company'))

        if len(name) < 3 or len(name) > 100:
            flash('Название компании должно быть от 3 до 100 символов', 'error')
            return redirect(url_for('create_company'))

        company = Company(
            name=name,
            market_cap=market_cap,
            staff=staff,
            owner_id=user.id
        )
        db.session.add(company)
        db.session.commit()

        flash(f'Компания "{name}" успешно создана!', 'success')
        return redirect(url_for('index'))

    return render_template('create_company.html', user=user)


@app.route('/delete_company', methods=['POST'])
@login_required
@log_activity('Удаление компании')
def delete_company():
    user = User.query.get(session['user_id'])
    if not user.company:
        flash('У вас нет компании для удаления', 'error')
        return render_template('index.html', user=user, company=None)

    try:
        Project.query.filter_by(company_id=user.company.id).delete()
        Customer.query.filter_by(company_id=user.company.id).delete()
        Programmer.query.filter_by(company_id=user.company.id).delete()
        TechnicalSupport.query.filter_by(company_id=user.company.id).delete()

        db.session.delete(user.company)
        db.session.commit()

        flash('Компания и все связанные данные успешно удалены', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении компании: {str(e)}', 'error')

    return render_template('index.html', user=user, company=None)


@app.route('/add_project', methods=['GET', 'POST'])
@login_required
def add_project():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    customers = Customer.query.filter_by(company_id=company.id).all()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        desc = request.form.get('description', '').strip()
        customer_id = request.form.get('customer')

        if not name or not desc or not customer_id:
            flash('Заполните все поля', 'error')
        else:
            try:
                customer = Customer.query.get(int(customer_id))
                if not customer or customer.company_id != company.id:
                    raise ValueError

                project = Project(
                    project_name=name,
                    description=desc,
                    customer_id=customer.id,
                    company_id=company.id
                )
                db.session.add(project)
                db.session.commit()
                flash('Проект успешно добавлен', 'success')
                return redirect(url_for('index'))
            except ValueError:
                flash('Некорректный клиент', 'error')

    return render_template('add_project.html',
                           user=user,
                           company=company,
                           customers=customers)


@app.route('/add_programmer', methods=['GET', 'POST'])
@login_required
@log_activity('Добавление программиста')
def add_programmer():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        salary = request.form.get('salary', '0').strip()
        sphere = request.form.get('sphere', '').strip()

        if not name or not salary or not sphere:
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('add_programmer'))

        try:
            salary = int(salary)
            if salary <= 0:
                raise ValueError
        except ValueError:
            flash('Зарплата должна быть положительным числом', 'error')
            return redirect(url_for('add_programmer'))

        if len(name) < 2 or len(name) > 50:
            flash('Имя должно быть от 2 до 50 символов', 'error')
            return redirect(url_for('add_programmer'))

        if sphere == 'QA':
            test_type = request.form.get('test_type', '').strip()
            automation = request.form.get('level_of_automation', '').strip()

            if not test_type or not automation:
                flash('Для QA-специалиста заполните все поля', 'error')
                return redirect(url_for('add_programmer'))

            programmer = Programmer(
                name=name,
                salary=salary,
                sphere=sphere,
                test_type=test_type,
                level_of_automation=automation,
                company_id=company.id
            )
        else:
            language = request.form.get('language', '').strip()
            quality = request.form.get('quality', '').strip()

            if not language or not quality:
                flash('Для разработчика заполните все поля', 'error')
                return redirect(url_for('add_programmer'))

            programmer = Programmer(
                name=name,
                salary=salary,
                sphere=sphere,
                programming_language=language,
                code_quality=quality,
                company_id=company.id
            )

        db.session.add(programmer)
        db.session.commit()

        flash(f'Программист {name} успешно добавлен', 'success')
        return redirect(url_for('index'))

    return render_template('add_programmer.html', user=user, company=company)


# Маршрут для добавления клиента
@app.route('/add_customer', methods=['GET', 'POST'])
@login_required
@log_activity('Добавление клиента')
def add_customer():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        contact = request.form.get('contact', '').strip()
        budget = request.form.get('budget', '0').strip()

        if not contact or not budget:
            flash('Заполните все поля', 'error')
            return redirect(url_for('add_customer'))

        try:
            budget = int(budget)
            if budget <= 0:
                raise ValueError
        except ValueError:
            flash('Бюджет должен быть положительным числом', 'error')
            return redirect(url_for('add_customer'))

        if len(contact) < 5 or len(contact) > 100:
            flash('Контактные данные должны быть от 5 до 100 символов', 'error')
            return redirect(url_for('add_customer'))

        customer = Customer(
            contact_details=contact,
            budget=budget,
            company_id=company.id
        )

        db.session.add(customer)
        db.session.commit()

        flash(f'Клиент {contact} успешно добавлен', 'success')
        return redirect(url_for('index'))

    return render_template('add_customer.html', user=user, company=company)


# Маршрут для добавления тех поддержки
@app.route('/add_tech_support', methods=['GET', 'POST'])
@login_required
@log_activity('Добавление техподдержки')
def add_tech_support():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        area = request.form.get('area', '').strip()
        tools = request.form.get('tools', '').strip()

        if not area or not tools:
            flash('Заполните все поля', 'error')
            return redirect(url_for('add_tech_support'))

        if len(area) < 3 or len(area) > 100:
            flash('Область ответственности должна быть от 3 до 100 символов', 'error')
            return redirect(url_for('add_tech_support'))

        if len(tools) < 3:
            flash('Укажите хотя бы один инструмент', 'error')
            return redirect(url_for('add_tech_support'))

        tech_support = TechnicalSupport(
            responsibility_area=area,
            tools_used=tools,
            company_id=company.id
        )

        db.session.add(tech_support)
        db.session.commit()

        flash('Техническая поддержка успешно добавлена', 'success')
        return redirect(url_for('index'))

    return render_template('add_tech_support.html', user=user, company=company)


# Маршрут для удаления проекта
@app.route('/delete_project/<int:project_id>', methods=['GET', 'POST'])
@login_required
@log_activity('Удаление проекта')
def delete_project(project_id):
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    project = Project.query.filter_by(id=project_id, company_id=company.id).first()

    if not project:
        flash('Проект не найден', 'error')
        return redirect(url_for('index'))

    db.session.delete(project)
    db.session.commit()

    flash('Проект успешно удален', 'success')
    return redirect(url_for('index'))


@app.route('/manage_project/<int:project_id>', methods=['GET', 'POST'])
@login_required
@log_activity('Управление проектом')
def manage_project(project_id):
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    project = Project.query.filter_by(id=project_id, company_id=company.id).first()

    if not project:
        flash('Проект не найден', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')

        try:
            if action == 'analyze':
                if project.analyze_requirements():
                    flash("Требования успешно проанализированы!", "success")
                else:
                    flash("Требования уже проанализированы", "info")

            elif action == 'develop':
                if not company.programmers:
                    flash("Нет программистов для разработки!", "error")
                    return redirect(url_for('manage_project', project_id=project_id))

                developer_id = request.form.get('developer')
                if not developer_id:
                    flash("Выберите программиста!", "error")
                    return redirect(url_for('manage_project', project_id=project_id))

                developer = Programmer.query.get(developer_id)
                if not developer or developer.company_id != company.id:
                    flash("Некорректный выбор программиста!", "error")
                elif project.develop_code(developer):
                    flash("Разработка кода начата!", "success")
                else:
                    flash("Код уже разработан", "info")

            elif action == 'test':
                if project.test_code():
                    flash("Тестирование завершено!", "success")
                else:
                    flash("Проект уже протестирован", "info")

            elif action == 'deploy':
                if not company.tech_supports:
                    flash("Нет технической поддержки для внедрения!", "error")
                    return redirect(url_for('manage_project', project_id=project_id))

                tech_support_id = request.form.get('tech_support')
                duration = request.form.get('duration')

                if not tech_support_id or not duration:
                    flash("Выберите техподдержку и укажите продолжительность!", "error")
                    return redirect(url_for('manage_project', project_id=project_id))

                try:
                    tech_support = TechnicalSupport.query.get(tech_support_id)
                    if not tech_support or tech_support.company_id != company.id:
                        raise ValueError

                    duration = int(duration)
                    project.deploy_and_support(tech_support, duration)
                    flash("Проект внедрен, поддержка назначена!", "success")
                except (ValueError, IndexError):
                    flash("Некорректный выбор техподдержки или продолжительности!", "error")

            elif action == 'train':
                if project.train_users():
                    flash("Обучение пользователей завершено!", "success")
                else:
                    flash("Пользователи уже обучены", "info")

        except ValueError as e:
            flash(str(e), "error")

        return redirect(url_for('manage_project', project_id=project_id))

    programmers = Programmer.query.filter_by(company_id=company.id).all()
    tech_supports = TechnicalSupport.query.filter_by(company_id=company.id).all()

    return render_template('manage_project.html',
                           project=project,
                           company=company,
                           programmers=programmers,
                           tech_supports=tech_supports,
                           user=user)


# Маршрут для списка программистов
@app.route('/programmers')
@login_required
def list_programmers():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    programmers = Programmer.query.filter_by(company_id=company.id).all()
    return render_template('programmers.html', programmers=programmers)


# Маршрут для списка клиентов
@app.route('/customers')
@login_required
def list_customers():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    customers = Customer.query.filter_by(company_id=company.id).all()
    return render_template('customers.html', customers=customers)


# Маршрут для списка техподдержки
@app.route('/tech_supports')
@login_required
def list_tech_supports():
    user = User.query.get(session['user_id'])
    company = user.company

    if not company:
        flash('Сначала создайте компанию', 'error')
        return redirect(url_for('index'))

    tech_supports = TechnicalSupport.query.filter_by(company_id=company.id).all()
    return render_template('tech_supports.html', tech_supports=tech_supports)


@app.route('/notifications')
@login_required
def view_notifications():
    user = User.query.get(session['user_id'])
    notifications = Notification.query.filter_by(user_id=user.id)\
        .order_by(Notification.created_at.desc())\
        .limit(50)\
        .all()
    return render_template('notifications.html',
                         notifications=notifications,
                         user=user,
                         company=user.company)


@app.route('/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=session['user_id'], is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()

    app.run(debug=True)