# ============== INIT ==============
# Flask
from flask import Flask, request, flash, redirect, render_template, g

# # Forms
from werkzeug.datastructures import MultiDict

# # Minify
from flask_minify import minify

# # Bootstrap
from flask_bootstrap import Bootstrap

# # Nav
from flask_nav import Nav
from flask_nav.elements import Navbar, View

# # Database
from flask_sqlalchemy import SQLAlchemy

# # Zoom
import base64
import threading

# Various
import os
import requests
from user_agents import parse as ua_parse

# Timing
from time import time, sleep

# Init flask
app = Flask(__name__, template_folder="files")
# # Forms
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["RECAPTCHA_USE_SSL"] = True
app.config["RECAPTCHA_PUBLIC_KEY"] = "6LfkR8QZAAAAAGURj6SFH7ZHulQz9HKLiMqI1Sxi"
app.config["RECAPTCHA_PRIVATE_KEY"] = os.getenv("CAPTCHA_KEY")
app.config["RECAPTCHA_DATA_ATTRS"] = {"theme": "dark"}
# # Minify
minify(app=app, html=True, js=True, cssless=True, static=True, caching_limit=0)
# # Bootstrap
Bootstrap(app)
# # Nav
nav = Nav()
nav.register_element("top", Navbar("HAZF", View("Home", "hello"), View("New", "setup"),))
nav.init_app(app)
# # Database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column("user_id", db.Integer, primary_key=True)
    url = db.Column(db.String(80))
    token = db.Column(db.String(642))
    refresh = db.Column(db.String(642))
    email = db.Column(db.String(60))

    def __repr__(self):
        return f"User {self.email} at {self.url}"


# Continous cycle
def stuffcycle():
    while True:
        requests.get("https://ha-zoom-forwarder.herokuapp.com/")
        sleep(60 * 20)


# Start async stuff
fc = threading.Thread(target=stuffcycle, daemon=True)
fc.start()

# Form
from flask_wtf import FlaskForm, RecaptchaField, Recaptcha
from wtforms import TextField, BooleanField, SubmitField
from wtforms.validators import Email, URL, DataRequired, InputRequired, ValidationError
import re


@app.before_request
def before_req():
    if "debuggy" not in globals():
        g.before_before_request_time = time() * 1000
        g.before_handle_request_time = time() * 1000
        g.after_request_time = time() * 1000
        if request.headers["X-Forwarded-Proto"] == "http":
            return redirect(request.url.replace("http", "https"), code=301)
        ua = None
        ua_add = ""
        if "User-Agent" in request.headers:
            ua = request.headers["User-Agent"]
            ua_add = ", " + str(ua_parse(ua))
        ip = request.headers["X-Forwarded-For"]
        print("Hit from " + ip + ua_add)
        chunks = request.url.split("/")
        g.before_handle_request_time = time() * 1000


@app.after_request
def after_req(response):
    response.headers[
        "Content-Security-Policy"
    ] = "default-src https: 'unsafe-eval' 'unsafe-inline'; object-src 'none'"
    if response.status_code != 301:
        response.headers[
            "Strict-Transport-Security"
        ] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if "debuggy" not in globals():
        response.headers["Server-Timing"] = 'beforereq;desc="Handle before request";dur='
        response.headers["Server-Timing"] += str(
            round(g.before_handle_request_time - g.before_before_request_time, 1)
        )
        response.headers["Server-Timing"] += ', process;desc="Render stuff";dur='
        g.after_request_time = time() * 1000
        response.headers["Server-Timing"] += str(
            round(g.after_request_time - g.before_handle_request_time, 1)
        )
    return response


# =============== FORM ==============


def check_url(form, field):
    try:
        res = requests.get(field.data, timeout=1)
        res.raise_for_status()
    except Exception as e:
        print(e)
        raise ValidationError("That's an unconnectable URL.")
    if len(field.data.split("/")) > 4:
        raise ValidationError("That's not a base URL.")
    elif field.data.count("/") == 2:
        raise ValidationError("That's a URL without a trailing slash.")


def check_captcha(form, field):
    res = requests.post(
        "https://www.google.com/recaptcha/api/siteverify",
        data={
            "secret": os.getenv("CAPTCHA_KEY"),
            "response": request.form.get("g-recaptcha-response", ""),
            "remoteip": request.headers["X-Forwarded-For"],
        },
    )
    print(res.json())
    if not res.json()["success"]:
        print("Invalid recaptcha.")
        raise ValidationError("That's an unchecked box.")


class RegisterForm(FlaskForm):
    url = TextField(
        "Home Assistant URL",
        [
            InputRequired("What do you think you're getting away with? Fill in all fields."),
            URL(message="That's an invalid URL."),
            check_url,
        ],
    )
    age = BooleanField(
        "I'm >13 (so I have permission to store your email)", validators=[DataRequired()]
    )
    recaptcha = RecaptchaField(
        "I'm not a robot spammer, or a spammer robot, or a spammer human, or a human spammer",
        validators=[check_captcha],
    )
    submit = SubmitField("Add / edit")


# ========== WEB INTERFACE ==========
# redirect to setup
@app.route("/setup")
def setup():
    return redirect(
        "https://zoom.us/oauth/authorize?response_type=code&client_id=n4gjRU19TeGm0YQDf47FdA&redirect_uri=https%3A%2F%2Fha-zoom-forwarder.herokuapp.com%2Fthanks",
        code=302,
    )


# home
@app.route("/")
def hello():
    return render_template("home.html")


# thanks
@app.route("/thanks", methods=["GET", "POST"])
def thanks():
    if "code" in dict(request.args) or "code" in dict(request.form):
        token = dict(request.args)["code"]
        form = RegisterForm()
        if request.method == "POST":
            if not form.validate():
                print(request.form)
                print(form.errors)
                print("Invalid.")
                return render_template("new.html", form=form)
            else:
                tokendata = requests.post(
                    "https://zoom.us/oauth/token",
                    params={
                        "grant_type": "authorization_code",
                        "code": token,
                        "redirect_uri": "https://ha-zoom-forwarder.herokuapp.com/thanks",
                    },
                    headers={
                        "Authorization": "Basic "
                        + base64.b64encode(
                            ("n4gjRU19TeGm0YQDf47FdA" + ":" + os.getenv("ZOOM_SECRET")).encode()
                        ).decode()
                    },
                ).json()
                print(tokendata)
                userdata = requests.get(
                    "https://api.zoom.us/v2/users",
                    headers={"Authorization": "Bearer " + tokendata["access_token"]},
                ).json()["users"][0]
                print(userdata)
                user = User(
                    url=request.form["url"],
                    token=tokendata["access_token"],
                    refresh=tokendata["refresh_token"],
                    email=userdata["email"],
                )
                print(user)
                db.session.add(user)
                db.session.commit()
                print(User.query.all())
                return "It works!"
        else:
            return render_template("new.html", form=form)
    else:
        return "I couldn't find a token."


# webhook
@app.route("/webhookstatus", methods=["POST"])
def webhook():
    print(request.method, request.data, request.form)
    return ""


# 404
@app.errorhandler(404)
def err404(e):
    if request.url[len(request.url) - 1] == "/":
        return redirect(request.url[0 : len(request.url) - 1], code=301)
    return "404: I dunno why that page isn't there.", 404


# 500
@app.errorhandler(500)
def err500(e):
    return (
        "500: There's a bug! But don't worry, it's inside Heroku, not you. It'll probably soon get fixed.",
        500,
    )


# if "DATABASE_URL" in dict(os.environ):
#    db.create_all()
