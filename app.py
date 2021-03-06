# ============== INIT ==============
# Flask
from flask import Flask, make_response, request, flash, redirect, render_template, g

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

# # Various
import os
import requests
import random
import json
from user_agents import parse as ua_parse

# # Zoom
import base64
import threading

appauth = {
    "Authorization": "Basic "
    + base64.b64encode(
        ("n4gjRU19TeGm0YQDf47FdA" + ":" + os.getenv("ZOOM_SECRET", "")).encode()
    ).decode()
}


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
    __mapper_args__ = {"confirm_deleted_rows": False}

    id = db.Column("user_id", db.Integer, primary_key=True)
    url = db.Column(db.String(80))
    token = db.Column(db.String(1000))
    refresh = db.Column(db.String(1000))
    email = db.Column(db.String(60), unique=True)
    webhook = db.Column(db.String(60), unique=True)

    def __repr__(self):
        return f"User {self.email} at {self.url}"


def decontaminate(email=None):
    users = User.query.all()
    users.reverse()
    emails = []
    for auser in users:
        works = False
        if email is None:
            works = auser.email not in emails
        else:
            works = auser.email != email
        if works:
            emails.append(auser.email)
        else:
            db.session.delete(auser)
    db.session.commit()


# Continous cycle
def stuffcycle():
    while True:
        #requests.get("https://ha-zoom-forwarder.herokuapp.com/")
        decontaminate()
        sleep(random.random() * 10.0)
        changed = False
        for user in User.query.all():
            tokendata = requests.post(
                "https://zoom.us/oauth/token",
                params={"grant_type": "refresh_token", "refresh_token": user.refresh},
                headers=appauth,
            ).json()
            if "access_token" in tokendata and "refresh_token" in tokendata:
                newuser = User(
                    url=user.url,
                    token=tokendata["access_token"],
                    refresh=tokendata["refresh_token"],
                    email=user.email,
                )
                db.session.add(newuser)
                changed = True
                print("Refreshed", newuser)
            db.session.delete(user)
        if changed:
            db.session.commit()
        sleep(random.randint(490, 690))


# Start async stuff
fc = threading.Thread(target=stuffcycle, daemon=True)
fc.start()

# Form
from flask_wtf import FlaskForm, RecaptchaField, Recaptcha
from wtforms import TextField, BooleanField, SubmitField
from wtforms.validators import Email, URL, DataRequired, InputRequired, ValidationError, Length
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
    if not res.json()["success"]:
        print("Invalid recaptcha.")
        raise ValidationError("That's an unchecked box.")


class RegisterForm(FlaskForm):
    url = TextField(
        "Home Assistant URL (to send webhook to)",
        [
            InputRequired("What do you think you're getting away with? Fill in all fields."),
            URL(message="That's an invalid URL."),
            check_url,
        ],
    )
    webhook = TextField(
        "Webhook ID",
        [
            InputRequired("What do you think you're getting away with? Fill in all fields."),
            Length(min=10, message="You don't want a hacker to guess your webhook, do you?"),
        ],
    )
    age = BooleanField(
        "I'm >13 (so I have permission to store your email)", validators=[DataRequired("So you're trying to get away with sharing your personal info?")]
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
    return render_template("setup.html")


# home
@app.route("/")
def hello():
    return render_template("home.html")


# new
@app.route("/new", methods=["GET", "POST"])
def new():
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
                        "redirect_uri": "https://ha-zoom-forwarder.herokuapp.com/new",
                    },
                    headers=appauth,
                ).json()
                userdata = requests.get(
                    "https://api.zoom.us/v2/users",
                    headers={"Authorization": "Bearer " + tokendata["access_token"]},
                ).json()["users"][0]
                user = User(
                    url=request.form["url"],
                    token=tokendata["access_token"],
                    refresh=tokendata["refresh_token"],
                    email=userdata["email"],
                    webhook=userdata["webhook"],
                )
                decontaminate(email=userdata["email"])
                db.session.add(user)
                db.session.commit()
                return "It works!"
        else:
            return render_template("new.html", form=form)
    else:
        return "I couldn't find a token."


# webhook
@app.route("/webhookstatus", methods=["POST"])
def webhook():
    webhook_info = request.data.decode()
    webhook_info = json.loads(webhook_info)
    if request.headers["Authorization"] == os.environ.get("ZOOM_VERIFY") and webhook_info[
        "payload"
    ]["object"]["email"] in [user.email for user in User.query.all()]:
        users = {user.email: user for user in User.query.all()}
        user = users[webhook_info["payload"]["object"]["email"]]
        print(user.url + "api/webhook/" + user.webhook, {"status": webhook_info["payload"]["object"]["presence_status"]})
        requests.get(user.url + "api/webhook/" + user.webhook, params={"status": webhook_info["payload"]["object"]["presence_status"]})
    else:
        print("Invalid:", webhook_info)
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
