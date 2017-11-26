from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
import os

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database

db = SQL("sqlite:///{}".format(os.path.join(os.path.dirname(__file__), "finance.db")))

@app.route("/")
@login_required
def index():
    user = session["user_id"]
    stocks = db.execute("SELECT symbol, quantity FROM stocks WHERE user_id=:user", user=user)
    stock_value = 0
    for stock in stocks:
        stock_data = lookup(stock["symbol"])
        stock.update(stock_data)
        stock_value += stock["price"] * stock["quantity"]
    user_info = db.execute("SELECT * FROM users WHERE id=:user", user=user)[0]
    return render_template("index.html", stocks=stocks, cash=user_info["cash"], networth=stock_value + user_info["cash"], usd=usd)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    if request.method == "POST":
        user = session["user_id"]
        symbol = request.form.get("symbol")
        try:
            quantity = int(request.form.get("quantity"))
        except ValueError:
            return apology("Please enter a valid stock symbol and positive integer quantity")
        stock = lookup(symbol)

        if not stock or not quantity or quantity < 1:
            return apology("Please enter a valid stock symbol and positive integer quantity")

        cash = db.execute("SELECT cash FROM users WHERE id=:user", user=user)[0]["cash"]
        if cash - stock["price"] * quantity < 0.0:
            return apology("Insufficient funds")

        # add purchase to the stocks table
        existing_entry = db.execute("SELECT COUNT(user_id) FROM stocks WHERE user_id=:user AND symbol=:symbol",
                                    user=user, symbol=symbol)
        if existing_entry[0]["COUNT(user_id)"] == 0:
            # user does not already own stocks for this stock
            db.execute("INSERT INTO stocks (user_id, symbol, quantity) VALUES (:user, :symbol, :quantity)",
                        user=user, symbol=symbol, quantity=quantity)
        else:
            # user does own stocks for this stock
            db.execute("UPDATE stocks SET quantity=quantity + :quantity WHERE user_id=:user AND symbol=:symbol",
                        quantity=quantity, user=user, symbol=symbol)

        # subtract purchase cost from users cash
        db.execute("UPDATE users SET cash=cash - :cost WHERE id=:user", cost=stock["price"] * quantity,
                    user=user)

        # log purchase in history
        db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, sale_time) VALUES (:user, :symbol, :quantity, :price, datetime('now'))", 
                    user=user, symbol=symbol, quantity=quantity, price=stock["price"])

        # redirect to home page
        return redirect(url_for("index"))
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""

    transactions = db.execute("SELECT * FROM transactions WHERE user_id=:user", user=session["user_id"])
    return render_template("history.html", transactions=transactions, usd=usd)    


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")     
        if symbol:
            stock = lookup(symbol)
            if stock:
                # if we got results for the input stock symbol display it
                return render_template("quoted.html", stock=stock, usd=usd)
            else:
                apology("Invalid stock symbol")             
        else:
            apology("Invalid stock symbol")

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    
    # log the user out if they're logged in
    session.clear()
    
    if request.method == "POST":
        if not request.form.get("username") or not request.form.get("password"):
            return apology("Please enter a username and password!")
        
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match!")
            
        user = request.form.get("username")
        password = pwd_context.hash(request.form.get("password"))
        
        response = db.execute("INSERT INTO users (username, hash) VALUES (:user, :password)", user=user, password=password)
        
        return redirect(url_for("login"))
        
    
    return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":
        user = session["user_id"]
        symbol = request.form.get("symbol")
        try:
            quantity = int(request.form.get("quantity"))
        except ValueError:
            return apology("Please enter a valid stock symbol and positive integer quantity")
        stock = lookup(symbol)

        if not stock or not quantity or quantity < 1:
            return apology("Please enter a valid stock symbol and positive integer quantity")

        user_quantity = db.execute("SELECT quantity FROM stocks WHERE user_id=:user AND symbol=:symbol", user=user, symbol=symbol)
        try:
            user_quantity = user_quantity[0]["quantity"]
        except IndexError:
            return apology("You don't own any of these stocks")

        if quantity > user_quantity:
            # if they enter more than they have then sell all stocks
            quantity = user_quantity


        # user does own stocks for this stock
        db.execute("UPDATE stocks SET quantity=quantity - :quantity WHERE user_id=:user AND symbol=:symbol", quantity=quantity, user=user, symbol=symbol)
        db.execute("DELETE FROM stocks WHERE user_id=:user AND symbol=:symbol AND quantity<1", user=user, symbol=symbol) # delete stock if all sold

        # subtract purchase cost from users cash
        db.execute("UPDATE users SET cash=cash + :cost WHERE id=:user", cost=stock["price"] * quantity, user=user)

        # log purchase in history
        db.execute("INSERT INTO transactions (user_id, symbol, quantity, price, sale_time) VALUES (:user, :symbol, :quantity, :price, datetime('now'))", 
                    user=user, symbol=symbol, quantity=-quantity, price=stock["price"])

        # redirect to home page
        return redirect(url_for("index"))
    else:
        return render_template("sell.html")

@app.route("/changepw", methods=["GET", "POST"])
@login_required
def changepw():
    if request.method == "POST":
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not password or password != confirmation:
            return apology("Please enter two maching passwords!")

        db.execute("UPDATE users SET hash=:password WHERE id=:user", password=pwd_context.hash(password), user=session["user_id"])
        session.clear()

        return redirect(url_for("login"))
    else:
        return render_template("changepw.html")
