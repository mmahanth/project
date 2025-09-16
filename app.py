from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import urllib.parse
from datetime import datetime

app = Flask(__name__)

# Database connection
DB_USER = "postgres"
DB_PASS = urllib.parse.quote_plus("Amurta@2024")
DB_HOST = "192.168.1.113"
DB_PORT = "5432"
DB_NAME = "intern_project"

app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# Employee Model
class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    emp_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    salary = db.Column(db.Float, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    department = db.Column(db.String(50), nullable=False)
    join_date = db.Column(db.Date, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "emp_id": self.emp_id,
            "name": self.name,
            "salary": self.salary,
            "email": self.email,
            "department": self.department,
            "join_date": (
                self.join_date.strftime("%d-%b-%Y") if self.join_date else None
            ),
        }


@app.route("/")
def index():
    return render_template("index.html")


# Create user
@app.route("/create_user", methods=["POST"])
def create_user():
    data = request.get_json()
    try:
        if Employee.query.filter_by(emp_id=data.get("emp_id")).first():
            return jsonify({"status": "error", "message": "Employee ID already exists"}), 400
        if Employee.query.filter_by(email=data.get("email")).first():
            return jsonify({"status": "error", "message": "Email already exists"}), 400

        join_date = (
            datetime.strptime(data.get("join_date"), "%Y-%m-%d").date()
            if data.get("join_date")
            else None
        )

        new_user = Employee(
            emp_id=data.get("emp_id"),
            name=data.get("name"),
            salary=float(data.get("salary")),
            email=data.get("email"),
            department=data.get("department"),
            join_date=join_date,
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"status": "success", "message": "User created successfully!"}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400


# Get users
@app.route("/get_user", methods=["GET"])
def get_users():
    employees = Employee.query.order_by(Employee.id.asc()).all()
    return jsonify({"status": "success", "data": [emp.to_dict() for emp in employees]})


# Update user
@app.route("/update_user/<int:id>", methods=["PUT"])
def update_user(id):
    data = request.get_json()
    try:
        emp = Employee.query.get(id)
        if not emp:
            return jsonify({"status": "error", "message": "Employee not found"}), 404

        emp.name = data.get("name", emp.name)
        emp.salary = float(data.get("salary", emp.salary))
        emp.email = data.get("email", emp.email)
        emp.department = data.get("department", emp.department)

        if data.get("join_date"):
            emp.join_date = datetime.strptime(data["join_date"], "%Y-%m-%d").date()

        db.session.commit()
        return jsonify({"status": "success", "message": "Employee updated!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400


# Delete user
@app.route("/delete_user/<int:id>", methods=["DELETE"])
def delete_user(id):
    try:
        emp = Employee.query.get(id)
        if not emp:
            return jsonify({"status": "error", "message": "Employee not found"}), 404
        db.session.delete(emp)
        db.session.commit()
        return jsonify({"status": "success", "message": "Employee deleted!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    print("Routes:", app.url_map)
    app.run(debug=True)

