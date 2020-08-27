# ============== INIT ==============
# Flask
from flask import Flask, request, flash, redirect, render_template, g
from flask_minify import minify
from flask_bootstrap import Bootstrap
from flask_nav import Nav
from flask_nav.elements import Navbar, View

# Various
import os
from user_agents import parse as ua_parse

# Server-side timing
from time import time

# Init flask
app = Flask(__name__, template_folder="files")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
minify(app=app, html=True, js=True, cssless=True, static=True, caching_limit=0)
Bootstrap(app)
nav = Nav()
# Form
from flask_wtf import FlaskForm
from wtforms import TextField, SubmitField
from wtforms.validators import Email, URL, Required, ValidationError
import re
import requests


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
        raise ValidationError("That's an unconnectable URL.")


class RegisterForm(FlaskForm):
    url = TextField(
        "Home Assistant URL",
        [
            Required("What do you think you're getting away with? Fill in all fields."),
            URL(message="That's an invalid URL."),
            check_url,
        ],
    )
    email = TextField(
        "Zoom account email",
        [
            Required("What do you think you're getting away with? Fill in all fields."),
            Email(check_deliverability=True, message="That's an invalid email."),
        ],
    )
    submit = SubmitField("Add / edit")


# ========== WEB INTERFACE ==========
# home
@app.route("/")
def hello():
    return render_template("home.html")


# new
@app.route("/new", methods=["GET", "POST"])
def new():
    form = RegisterForm()
    if request.method == "POST":
        if not form.validate():
            return render_template("new.html", form=form)
        else:
            return redirect("/", code=302)
    else:
        return render_template("new.html", form=form)


# card
@app.route("/webhook/<theid>")
def card(theid):
    return render_template("play.html", uid=theid)


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


# navbar
nav.register_element("top", Navbar("HAZF", View("Home", "/"), View("New", "/new"),))
nav.init_app(app)
