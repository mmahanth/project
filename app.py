import logging
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, send_file, abort, flash
import io
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import gridfs
from bson import ObjectId
from datetime import datetime, timedelta
from functools import wraps
import urllib.parse
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

logging.basicConfig(level=logging.DEBUG)

# ------------------- Database Setup -------------------
DB_USER = "postgres"
DB_PASS = urllib.parse.quote_plus("Amurta@2024")
DB_HOST = "192.168.1.113"
DB_PORT = "5432"
DB_NAME = "intern_project"

app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# MongoDB for file storage
mongo_client = MongoClient("mongodb://localhost:27017")
mongo_db = mongo_client["Artha"]
fs = gridfs.GridFS(mongo_db)


# ------------------- Models -------------------
class Employee(db.Model):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    salary = db.Column(db.Float, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    department = db.Column(db.String(50), nullable=False)
    join_date = db.Column(db.Date, nullable=True)
    image_file_id = db.Column(db.String(24), nullable=True)
    cv_file_id = db.Column(db.String(24), nullable=True)
    other_file_id = db.Column(db.String(24), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "emp_id": self.emp_id,
            "name": self.name,
            "salary": self.salary,
            "email": self.email,
            "department": self.department,
            "join_date": self.join_date.strftime("%d-%m-%Y") if self.join_date else None,
            "image_file_id": self.image_file_id,
            "cv_file_id": self.cv_file_id,
            "other_file_id": self.other_file_id,
        }

    def get_other_files(self):
        """Return a list of other file IDs from the stored comma-separated string."""
        if not self.other_file_id:
            return []
        return [fid.strip() for fid in self.other_file_id.split(',') if fid.strip()]


class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # ⚠️ Use hashing in production!
    role = db.Column(db.String(50), nullable=False)
    emp_id = db.Column(db.String(20), db.ForeignKey("employees.emp_id"), nullable=True)

    def set_password(self, password):
        self.password = password

    def check_password(self, password):
        return self.password == password


class Timesheet(db.Model):
    __tablename__ = "timesheets"
    id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.String(20), db.ForeignKey("employees.emp_id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=True)
    break_duration = db.Column(db.Integer, default=0)  # minutes
    total_hours = db.Column(db.Float, nullable=True)
    task_description = db.Column(db.Text, nullable=True)
    project_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default="in_progress")  # in_progress, completed, submitted
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Add unique constraint to prevent duplicate entries for same employee on same date
    __table_args__ = (db.UniqueConstraint('emp_id', 'date', name='unique_emp_date'),)

    def to_dict(self):
        return {
            "id": self.id,
            "emp_id": self.emp_id,
            "date": self.date.strftime("%Y-%m-%d") if self.date else None,
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else None,
            "end_time": self.end_time.strftime("%H:%M") if self.end_time else None,
            "break_duration": self.break_duration,
            "total_hours": self.total_hours,
            "task_description": self.task_description,
            "project_name": self.project_name,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


# ------------------- Decorators -------------------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)

    return decorated


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "user_role" not in session or session["user_role"] not in roles:
                abort(403)
            return f(*args, **kwargs)

        return decorated

    return decorator


# ------------------- Routes -------------------
@app.route("/")
def home():
    if "user_id" in session:
        if session.get("user_role") == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("user_dashboard"))
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html", error=None)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        error = "Invalid username or password"
        return render_template("login.html", error=error)
    session["user_id"] = user.id
    session["user_role"] = user.role
    session["emp_id"] = user.emp_id
    if user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ------------------- CRUD API -------------------
@app.route("/update_user/<int:user_id>", methods=["PUT"])
@login_required
@roles_required("admin")
def update_user(user_id):
    employee = Employee.query.get_or_404(user_id)
    data = request.get_json()
    try:
        if 'emp_id' in data and data['emp_id'] != employee.emp_id:
            if Employee.query.filter_by(emp_id=data['emp_id']).first():
                return jsonify({"status": "error", "message": "Employee ID already exists"}), 400
            employee.emp_id = data['emp_id']
        if 'name' in data:
            employee.name = data['name']
        if 'email' in data:
            employee.email = data['email']
        if 'department' in data:
            employee.department = data['department']
        if 'salary' in data:
            employee.salary = float(data['salary'])
        if 'join_date' in data and data['join_date']:
            # Accept ISO format YYYY-MM-DD here
            employee.join_date = datetime.strptime(data['join_date'], "%Y-%m-%d")
        else:
            employee.join_date = None
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Employee updated successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/create_user", methods=["POST"])
@login_required
@roles_required("admin")
def create_user():
    data = request.get_json()
    try:
        if Employee.query.filter_by(emp_id=data['emp_id']).first():
            return jsonify({"status": "error", "message": "Employee ID already exists"}), 400
        join_date = None
        if data.get('join_date'):
            # Accept join_date as DD-MM-YYYY
            join_date = datetime.strptime(data['join_date'], "%d-%m-%Y")
        employee = Employee(
            emp_id=data['emp_id'],
            name=data['name'],
            email=data['email'],
            department=data['department'],
            salary=float(data['salary']),
            join_date=join_date
        )
        db.session.add(employee)
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Employee created successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/delete_user/<int:user_id>", methods=["DELETE"])
@login_required
@roles_required("admin")
def delete_user(user_id):
    try:
        employee = Employee.query.get_or_404(user_id)
        db.session.delete(employee)
        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Employee deleted successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------- API to fetch users -------------------
@app.route("/get_users")
@login_required
@roles_required("admin")
def get_users():
    try:
        q = Employee.query
        search = request.args.get("search")
        if search:
            q = q.filter(
                (Employee.name.ilike(f"%{search}%"))
                | (Employee.email.ilike(f"%{search}%"))
                | (Employee.department.ilike(f"%{search}%"))
            )
        employees = q.all()
        data = [e.to_dict() for e in employees]
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        app.logger.error(f"Error loading employees: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ------------------- File Uploads -------------------
@app.route("/upload_files/<emp_id>", methods=["POST"])
@login_required
def upload_files(emp_id):
    # Limit upload access to owner or admin
    if session.get("role") != "admin" and session.get("emp_id") != emp_id:
        flash("Unauthorized to update this employee's files.", "error")
        return redirect(url_for("user_details"))

    employee = Employee.query.filter_by(emp_id=emp_id).first()
    if not employee:
        flash("Employee not found.", "error")
        return redirect(url_for("user_details"))

    try:
        # Replace profile image if new upload present
        image_file = request.files.get('profile_img')
        if image_file and image_file.filename:
            if not allowed_image_file(image_file.filename):
                flash("Profile image must be JPG or PNG.", "error")
                return redirect(url_for("user_details"))

            # Delete old image file on GridFS if exists
            if employee.image_file_id:
                try:
                    fs.delete(ObjectId(employee.image_file_id))
                except:
                    pass

            image_id = fs.put(image_file.read(), filename=secure_filename(image_file.filename),
                              content_type=image_file.content_type)
            employee.image_file_id = str(image_id)

        # Replace CV if new upload present
        cv_file = request.files.get('cv')
        if cv_file and cv_file.filename:
            if not allowed_cv_file(cv_file.filename):
                flash("CV must be a PDF document.", "error")
                return redirect(url_for("user_details"))

            if employee.cv_file_id:
                try:
                    fs.delete(ObjectId(employee.cv_file_id))
                except:
                    pass

            cv_id = fs.put(cv_file.read(), filename=secure_filename(cv_file.filename),
                           content_type=cv_file.content_type)
            employee.cv_file_id = str(cv_id)

        # Replace other docs - support multiple files
        other_files = request.files.getlist('other_docs[]')
        if other_files:
            # Delete old other files on GridFS
            if employee.other_file_id:
                old_ids = [id.strip() for id in employee.other_file_id.split(",") if id.strip()]
                for old_id in old_ids:
                    try:
                        fs.delete(ObjectId(old_id))
                    except:
                        pass

            new_ids = []
            for other_file in other_files:
                if other_file and other_file.filename and allowed_other_file(other_file.filename):
                    file_id = fs.put(other_file.read(), filename=secure_filename(other_file.filename),
                                     content_type=other_file.content_type)
                    new_ids.append(str(file_id))

            if new_ids:
                employee.other_file_id = ",".join(new_ids)

        db.session.commit()
        flash("Files uploaded successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Upload failed: {str(e)}", "error")

    return redirect(url_for("user_details"))


def allowed_image_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_cv_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'


def allowed_other_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------- FILE SERVE ----------
@app.route("/files/<file_id>")
def serve_file(file_id):
    try:
        file = fs.get(ObjectId(file_id))
        return send_file(
            io.BytesIO(file.read()),
            mimetype=file.content_type,
            download_name=file.filename,
            as_attachment=False,
        )
    except Exception:
        return "File not found", 404




# ------------------- Context Processor -------------------
@app.context_processor
def inject_datetime():
    from datetime import datetime, timedelta
    return {
        'datetime': datetime,
        'timedelta': timedelta
    }



# ------------------- Password Reset -------------------
@app.route("/reset_password", methods=["GET", "POST"])
@login_required
def reset_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        user = User.query.get(session["user_id"])
        if not user or not user.check_password(current_password):
            error = "Current password is incorrect."
            return render_template("reset_password.html", error=error)

        if new_password != confirm_password:
            error = "New password and confirm password do not match."
            return render_template("reset_password.html", error=error)

        user.set_password(new_password)
        db.session.commit()
        message = "Password updated successfully."
        return render_template("reset_password.html", message=message)

    return render_template("reset_password.html")


# ------------------- Dashboards -------------------
@app.route("/admin")
@login_required
@roles_required("admin")
def admin_dashboard():
    total_employees = Employee.query.count()
    return render_template("admin_dashboard.html", total_employees=total_employees, active='dashboard')


@app.route("/employee_management")
@login_required
@roles_required("admin")
def employee_management():
    employees = Employee.query.all()
    return render_template("employee_management.html", employees=employees, active='employees')


# Add this new route for admin to view employee files
@app.route("/admin/employees")
@login_required
@roles_required("admin")
def admin_employees():
    employees = Employee.query.all()
    return render_template("admin_employees.html", employees=employees)


# Add this API route for fetching employee files
@app.route("/admin/employee/<emp_id>/files")
@login_required
@roles_required("admin")
def admin_employee_files(emp_id):
    employee = Employee.query.filter_by(emp_id=emp_id).first_or_404()

    files = {
        'profile_image': None,
        'cv': None,
        'other_documents': []
    }

    if employee.image_file_id:
        files['profile_image'] = url_for('serve_file', file_id=employee.image_file_id)
    if employee.cv_file_id:
        files['cv'] = url_for('serve_file', file_id=employee.cv_file_id)
    if employee.other_file_id:
        file_ids = employee.get_other_files()
        for idx, file_id in enumerate(file_ids):
            if file_id.strip():
                files['other_documents'].append({
                    'name': f'Document {idx + 1}',
                    'url': url_for('serve_file', file_id=file_id.strip())
                })

    return jsonify(files)


@app.route("/user_management", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def user_management():
    employees = Employee.query.all()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        emp_id = request.form.get("emp_id")

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
        else:
            new_user = User(username=username, password=password, role=role, emp_id=emp_id)
            db.session.add(new_user)
            db.session.commit()
            flash("User created successfully!", "success")
        return redirect(url_for("user_management"))

    return render_template("user_management.html", employees=employees, active='users')


@app.route("/user")
@login_required
@roles_required("employee", "user")
def user_dashboard():
    emp = Employee.query.filter_by(emp_id=session.get("emp_id")).first()
    return render_template("user_dashboard.html", employee=emp)


@app.route("/attendees")
@login_required
def attendees():
    attendees = Employee.query.all()
    employee = Employee.query.filter_by(emp_id=session.get("emp_id")).first()

    # Calculate stats
    total_employees = len(attendees)
    it_employees = len([emp for emp in attendees if emp.department == 'IT'])
    hr_employees = len([emp for emp in attendees if emp.department == 'HR'])

    # Calculate new joiners (last 3 months)
    from datetime import datetime, timedelta
    three_months_ago = datetime.now().date() - timedelta(days=90)
    new_joiners = len([emp for emp in attendees if emp.join_date and emp.join_date > three_months_ago])

    return render_template("attendees.html",
                           attendees=attendees,
                           employee=employee,
                           total_employees=total_employees,
                           it_employees=it_employees,
                           hr_employees=hr_employees,
                           new_joiners=new_joiners)


@app.route("/user_details")
@login_required
def user_details():
    employee = Employee.query.filter_by(emp_id=session.get("emp_id")).first()
    return render_template("user_details.html", employee=employee)


# -----------------------Timesheet---------------
@app.route("/timesheet")
@login_required
@roles_required("employee", "user")
def timesheet():
    emp_id = session.get("emp_id")
    employee = Employee.query.filter_by(emp_id=emp_id).first()

    if not employee:
        flash("Employee record not found", "error")
        return redirect(url_for("user_dashboard"))

    # Get period from query parameter (default: current_week)
    period = request.args.get('period', 'current_week')

    today = datetime.now().date()

    if period == 'current_week':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        period_title = "This Week"
    elif period == 'last_week':
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
        period_title = "Last Week"
    elif period == 'current_month':
        start_date = today.replace(day=1)
        # Get last day of current month
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        period_title = "This Month"
    elif period == 'last_month':
        # Get first day of last month
        if today.month == 1:
            start_date = today.replace(year=today.year - 1, month=12, day=1)
            end_date = today.replace(day=1) - timedelta(days=1)
        else:
            start_date = today.replace(month=today.month - 1, day=1)
            end_date = today.replace(day=1) - timedelta(days=1)
        period_title = "Last Month"
    else:
        # Default to current week
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        period_title = "This Week"

    # Get timesheets for the selected period
    timesheets = Timesheet.query.filter(
        Timesheet.emp_id == emp_id,
        Timesheet.date >= start_date,
        Timesheet.date <= end_date
    ).order_by(Timesheet.date.desc()).all()

    # Calculate period days with timesheet data
    period_days = []
    current_date = start_date
    while current_date <= end_date:
        day_timesheet = next((t for t in timesheets if t.date == current_date), None)
        period_days.append({
            'date': current_date,
            'date_str': current_date.strftime('%Y-%m-%d'),
            'day_name': current_date.strftime('%a'),
            'day_number': current_date.strftime('%d'),
            'month_name': current_date.strftime('%b'),
            'timesheet': day_timesheet
        })
        current_date += timedelta(days=1)

    # Calculate statistics
    total_hours = sum([t.total_hours or 0 for t in timesheets])
    days_worked = len([t for t in timesheets if t.total_hours])
    avg_daily_hours = round(total_hours / len(period_days), 1) if len(period_days) > 0 else 0
    avg_working_day_hours = round(total_hours / days_worked, 1) if days_worked > 0 else 0

    return render_template("timesheet.html",
                           employee=employee,
                           timesheets=timesheets,
                           period_days=period_days,
                           total_hours=total_hours,
                           avg_daily_hours=avg_daily_hours,
                           avg_working_day_hours=avg_working_day_hours,
                           days_worked=days_worked,
                           period=period,
                           period_title=period_title,
                           start_date=start_date,
                           end_date=end_date,
                           today_date=datetime.now().strftime('%A, %B %d, %Y'))


# ------------------- Timesheet API Routes -------------------
@app.route("/api/timesheet/<int:timesheet_id>", methods=["GET"])
@login_required
@roles_required("employee", "user")
def get_timesheet(timesheet_id):
    try:
        emp_id = session.get("emp_id")
        print(f"Debug: Getting timesheet {timesheet_id} for emp_id: {emp_id}")

        if not emp_id:
            return jsonify({"success": False, "message": "Employee ID not found in session"}), 401

        timesheet = Timesheet.query.filter_by(id=timesheet_id, emp_id=emp_id).first()

        if not timesheet:
            # Check if timesheet exists for any employee (debug)
            any_timesheet = Timesheet.query.filter_by(id=timesheet_id).first()
            if any_timesheet:
                return jsonify({"success": False, "message": f"Timesheet belongs to different employee"}), 403
            else:
                return jsonify({"success": False, "message": "Timesheet not found"}), 404

        return jsonify({
            "success": True,
            "data": timesheet.to_dict()
        })

    except Exception as e:
        print(f"Error in get_timesheet: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


@app.route("/api/timesheet", methods=["POST"])
@login_required
@roles_required("employee", "user")
def add_timesheet():
    try:
        data = request.get_json()
        emp_id = session.get("emp_id")

        if not emp_id:
            return jsonify({"success": False, "message": "Employee ID not found in session"}), 401

        # Validate required fields
        required_fields = ['date', 'start_time', 'end_time']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"success": False, "message": f"{field} is required"}), 400

        # Parse date and times
        entry_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        end_time = datetime.strptime(data['end_time'], '%H:%M').time() if data.get('end_time') else None

        # Validate time logic
        if end_time and start_time >= end_time:
            return jsonify({"success": False, "message": "End time must be after start time"}), 400

        # Check if timesheet already exists for this date
        existing = Timesheet.query.filter_by(emp_id=emp_id, date=entry_date).first()
        if existing:
            return jsonify({"success": False, "message": "Timesheet already exists for this date"}), 409

        # Create new timesheet entry
        timesheet = Timesheet(
            emp_id=emp_id,
            date=entry_date,
            start_time=start_time,
            end_time=end_time,
            break_duration=int(data.get('break_duration', 0)),
            task_description=data.get('task_description', '').strip(),
            project_name=data.get('project_name', '').strip(),
            status=data.get('status', 'completed')
        )

        # Calculate total hours
        if timesheet.end_time:
            start_datetime = datetime.combine(timesheet.date, timesheet.start_time)
            end_datetime = datetime.combine(timesheet.date, timesheet.end_time)
            total_minutes = (end_datetime - start_datetime).total_seconds() / 60
            total_minutes -= timesheet.break_duration  # Subtract break time
            timesheet.total_hours = round(max(total_minutes / 60, 0), 2)  # Ensure non-negative

        db.session.add(timesheet)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Timesheet entry added successfully",
            "data": timesheet.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({"success": False, "message": f"Invalid date/time format: {str(e)}"}), 400
    except Exception as e:
        print(f"Error in add_timesheet: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error saving timesheet: {str(e)}"}), 500


@app.route("/api/timesheet/<int:timesheet_id>", methods=["PUT"])
@login_required
@roles_required("employee", "user")
def update_timesheet(timesheet_id):
    try:
        data = request.get_json()
        emp_id = session.get("emp_id")

        timesheet = Timesheet.query.filter_by(id=timesheet_id, emp_id=emp_id).first()
        if not timesheet:
            return jsonify({"success": False, "message": "Timesheet not found"}), 404

        # Update fields
        if data.get('start_time'):
            timesheet.start_time = datetime.strptime(data['start_time'], '%H:%M').time()
        if data.get('end_time'):
            timesheet.end_time = datetime.strptime(data['end_time'], '%H:%M').time()
        if 'break_duration' in data:
            timesheet.break_duration = int(data['break_duration'])
        if 'task_description' in data:
            timesheet.task_description = data['task_description'].strip()
        if 'project_name' in data:
            timesheet.project_name = data['project_name'].strip()
        if 'status' in data:
            timesheet.status = data['status']

        # Validate time logic
        if timesheet.end_time and timesheet.start_time >= timesheet.end_time:
            return jsonify({"success": False, "message": "End time must be after start time"}), 400

        # Recalculate total hours
        if timesheet.end_time:
            start_datetime = datetime.combine(timesheet.date, timesheet.start_time)
            end_datetime = datetime.combine(timesheet.date, timesheet.end_time)
            total_minutes = (end_datetime - start_datetime).total_seconds() / 60
            total_minutes -= timesheet.break_duration
            timesheet.total_hours = round(max(total_minutes / 60, 0), 2)

        timesheet.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Timesheet updated successfully",
            "data": timesheet.to_dict()
        })

    except ValueError as e:
        return jsonify({"success": False, "message": f"Invalid time format: {str(e)}"}), 400
    except Exception as e:
        print(f"Error in update_timesheet: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error updating timesheet: {str(e)}"}), 500


@app.route("/api/timesheet/<int:timesheet_id>", methods=["DELETE"])
@login_required
@roles_required("employee", "user")
def delete_timesheet(timesheet_id):
    try:
        emp_id = session.get("emp_id")
        timesheet = Timesheet.query.filter_by(id=timesheet_id, emp_id=emp_id).first()

        if not timesheet:
            return jsonify({"success": False, "message": "Timesheet not found"}), 404

        db.session.delete(timesheet)
        db.session.commit()

        return jsonify({"success": True, "message": "Timesheet deleted successfully"})

    except Exception as e:
        print(f"Error in delete_timesheet: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error deleting timesheet: {str(e)}"}), 500


# API endpoint to get timesheets for different periods
@app.route("/api/period_timesheets/<period>")
@login_required
@roles_required("employee", "user")
def get_period_timesheets(period):
    try:
        # Get logged in employee ID from session
        emp_id = session.get("emp_id")
        if not emp_id:
            return jsonify({"success": False, "message": "Not logged in"}), 401

        today = datetime.now().date()

        # Determine date range based on period parameter
        if period == 'current_week':
            # Current week's Monday-Sunday
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif period == 'last_week':
            # Previous week's Monday-Sunday
            start_date = today - timedelta(days=today.weekday() + 7)
            end_date = start_date + timedelta(days=6)
        elif period == 'current_month':
            # First and last day of current month
            start_date = today.replace(day=1)
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period == 'last_month':
            # First and last day of previous month
            if today.month == 1:
                # December previous year
                start_date = today.replace(year=today.year - 1, month=12, day=1)
                end_date = today.replace(day=1) - timedelta(days=1)
            else:
                start_date = today.replace(month=today.month - 1, day=1)
                end_date = today.replace(day=1) - timedelta(days=1)
        else:
            return jsonify({"success": False, "message": "Invalid period"}), 400

        # Query timesheets within date range for current employee
        timesheets = (Timesheet.query
                      .filter(Timesheet.emp_id == emp_id,
                              Timesheet.date >= start_date,
                              Timesheet.date <= end_date)
                      .order_by(Timesheet.date.desc())
                      .all())

        # Prepare JSON response data
        data = [t.to_dict() for t in timesheets]

        # Send response with timesheet data and date range info
        return jsonify({
            "success": True,
            "data": data,
            "period": period,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "count": len(data)
        })

    except Exception as e:
        print(f"Error in get_period_timesheets: {str(e)}")
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


# ------------------- Run -------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
