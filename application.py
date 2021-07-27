import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # query database to get cash on hand
    user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

    # query database to get current holdings from transactions list
    stocks = db.execute(
        "SELECT symbol, SUM(shares) AS shares, price FROM transactions WHERE user_id = :user_id GROUP BY symbol", user_id=session["user_id"])

    # assign names and totals for stocks
    for stock in stocks:
        stock_lookup = lookup(stock["symbol"])
        stock["name"] = stock_lookup["name"]
        stock["total"] = stock["shares"] * stock_lookup["price"]

    stocks[:] = [stock for stock in stocks if stock.get("shares") > 0]

    totals = user_cash + sum([stock["total"] for stock in stocks])

    return render_template("index.html", user_cash=user_cash, stocks=stocks, total=totals, usd=usd)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    def price_check(cash, price, shares):
        """check affordability of stock vs cash on hand"""
        affordable = (cash - (price * shares)) > 0

        if affordable:
            return affordable

        else:
            return False

    if request.method == "POST":

        stock = lookup(request.form.get("symbol"))

        # check symbol and share # are valid
        if not stock:
            return apology("Missing or Incorrect Symbol", 400)

        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("Input at least 1 share", 400)

        if shares < 0:
            return apology("Input at least 1 share", 400)


        # cast shares to int & fetch users cash on hand
        shares = int(request.form.get("shares"))
        user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

        if price_check(user_cash, stock["price"], shares) == False:
            return apology("Sorry, you can't afford this purchase.", 400)

        else:
            # define variables for inserting into transactions table
            purchase_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # update user cash
            user_cash = user_cash - (stock["price"]*shares)
            db.execute("UPDATE users SET cash = :user_cash WHERE id = :user_id", user_id=session["user_id"], user_cash=user_cash)

            # update transactions table with most recent transaction
            db.execute("""
                INSERT INTO transactions(user_id, date, symbol, shares, price)
                VALUES(:user_id, :date, :symbol, :shares, :price)
                """,
                        user_id=session["user_id"],
                        date=purchase_date,
                        symbol=stock["symbol"],
                        shares=shares,
                        price=stock["price"]
                        )

            return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # get all transactions for current user
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :user_id", user_id=session["user_id"])

    # render history.html with all user transactions
    return render_template("history.html", transactions=transactions, usd=usd)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock = lookup(symbol)

        if not stock:
            return apology("Invalid or missing symbol", 400)

        else:
            return render_template("quoted.html", stock=stock, usd=usd)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user id
    session.clear()

    if request.method == "POST":

        # check username field
        if not request.form.get("username"):
            return apology("Please enter a username", 400)

        # check password exists
        elif not request.form.get("password"):
            return apology("Please enter a password", 400)

        # check passwords match
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("Password's don't match", 400)

        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # check for duplicate username, if none, insert into finance.db
        if len(rows) != 0:
            return apology("Username already exists", 400)
        else:
            username = request.form.get("username")
            hashed = generate_password_hash(request.form.get("password"))
            db.execute("INSERT INTO users (username, hash) VALUES (:username, :hashed)", username=username, hashed=hashed)
            return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # define stock variables
        symbol = request.form.get("symbol")
        stock = lookup(request.form.get("symbol"))

        # error checking
        if not stock:
            return apology("Missing or Incorrect Symbol", 400)

        # check if stock is owned
        try:
            sold_stock = db.execute(
                "SELECT symbol, SUM(shares) AS shares, price FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol", user_id=session["user_id"], symbol=symbol)[0]
        except IndexError:
            return apology("Stock not owned", 400)

        # check for shares input
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("Input at least 1 share", 400)

        if shares < 0:
            return apology("Input at least 1 Share", 400)

        if int(sold_stock["shares"]) < shares:
            return apology("Not enough shares to sell", 400)

        else:
            # define variables for inserting into transactions table and updating cash
            purchase_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # update user cash
            user_cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]
            user_cash = user_cash + (stock["price"]*shares)
            db.execute("UPDATE users SET cash = :user_cash WHERE id = :user_id", user_id=session["user_id"], user_cash=user_cash)

            # update transactions table with selling transaction
            db.execute("""
                INSERT INTO transactions(user_id, date, symbol, shares, price)
                VALUES(:user_id, :date, :symbol, :shares, :price)
                """,
                        user_id=session["user_id"],
                        date=purchase_date,
                        symbol=stock["symbol"],
                        shares=-shares,
                        price=stock["price"]
                        )

            flash("You paper-handed that one!")
            return redirect("/")

    else:
        # query db for current holdings
        stocks = db.execute(
            "SELECT symbol, SUM(shares) AS shares, price FROM transactions WHERE user_id = :user_id GROUP BY symbol", user_id=session["user_id"])
        stocks[:] = [stock for stock in stocks if stock.get('shares') > 0]
        return render_template("sell.html", stocks=stocks)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
