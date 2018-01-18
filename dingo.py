from flask import Flask, flash, request, session, render_template, redirect, url_for, send_from_directory
from psycopg2 import connect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from os import urandom, path, environ
import random ##
from breed_classifier.inference.classify import infer
from breed_classifier.common import consts
from urllib import parse
from sys import argv


###everything needs to get redirected if not logged in etc.



app = Flask(__name__)
app.secret_key = urandom(24)


BREEDS = ["Golden Retriever", "English Setter", "Beagle", "Weimaraner"]






#######
def db_connect():
	if len(argv) == 1: ####only for testing do i need else
		parse.uses_netloc.append("postgres")
		url = parse.urlparse(environ["DATABASE_URL"])
		conn = connect(
			database=url.path[1:],
			user=url.username,
			password=url.password,
			host=url.hostname,
			port=url.port
		)
	else:
		conn = connect("dbname=dingo")
	return conn


##validator class...:

def validate_user(username, pw):
	conn = db_connect()
	curs = conn.cursor()
	curs.execute("""SELECT username, password FROM users WHERE username = %s;""", (username,))
	match = curs.fetchone()
	error_msg = None
	if not match:
		error_msg = "Username '{}' does not exist".format(username)
	elif not check_password_hash(match[1], pw):
		error_msg = "Incorrect password"
	conn.close()
	return error_msg






@app.route("/username_availability", methods=["POST"])
def username_availability():
	conn = db_connect()
	c = conn.cursor()
	username = request.form.get("username")
	c.execute("""SELECT username FROM users WHERE username = %s;""", (username,))
	match = c.fetchone()
	conn.close()
	if match:
		return "username_error"
	else:
		return "success"

@app.route("/email_availability", methods=["POST"])
def email_availability():
	conn = db_connect()
	c = conn.cursor()
	email = request.form.get("email")
	c.execute("""SELECT email FROM users WHERE email = %s;""", (email,))
	match = c.fetchone()
	conn.close()
	if match:
		return "email_error"
	else:
		return "success"






#########




@app.route("/", methods=["GET", "POST"])
def login():
	if request.method == "POST":
		username = request.form.get("username")
		pw = request.form.get("password")
		error_msg = validate_user(username, pw)
		if error_msg == None:
			session["username"] = username
			return redirect(url_for('user', username = username))
		else:
			return render_template("login.html", error_msg = error_msg)
	else:
		if "username" in session:
			return redirect(url_for('user', username = session["username"]))
		else:
			return render_template("login.html")











######################
######################


@app.route("/signup", methods=["GET", "POST"])
def signup():
	if request.method == "POST":
		username = request.form['username']
		email = request.form['email']
		pw = request.form["password"]
		conn = db_connect()
		c = conn.cursor()
		c.execute("""INSERT INTO users VALUES (%s, %s, %s);""", (username, generate_password_hash(pw), email))
		conn.commit()
		conn.close()
		session["username"] = username
		return redirect(url_for('user', username = username))
	elif "username" in session:
		return redirect(url_for('user', username = session["username"]))
	else:
		return render_template("signup.html")


@app.route("/logout")
def logout():
	session.clear()
	return redirect(url_for('login'))



@app.route("/user/<username>")
def user(username):
	if username != session.get("username"):
		return redirect(url_for('login'))
	conn = db_connect()
	c = conn.cursor()
	c.execute("""SELECT game_name FROM games 
		         WHERE username = %s 
		         ORDER BY join_date""", (username,))
	session["game_names"] = [match[0] for match in c.fetchall()]
	return render_template("games.html", username = username, game_names = session.get("game_names"))


@app.route("/user/<username>/<game_name>")
def game(username, game_name):
	if username != session.get("username"):
		return redirect(url_for('login'))

	conn = db_connect()
	c = conn.cursor()
	c.execute("""SELECT slot, filename from cards JOIN dogs ON cards.breed = dogs.breed WHERE username = %s AND game_name = %s""", (username, game_name))

	card = c.fetchall().sort()

	render_template("card.html", card=card, username=username, game_name=game_name)






@app.route("/create_game", methods=["GET", "POST"])
def create_game():
	if request.method == "POST":
		game_name = request.form["game_name"]
		if not game_name:
			return render_template("create_game.html", username=session.get("username"), game_name_error_msg = "Game name cannot be empty")
		invitees = {user.strip() for user in request.form["invitees"].split(",") if user}
		conn = db_connect()
		c = conn.cursor()
		c.execute("""SELECT game_name FROM games WHERE game_name = %s;""", (game_name,))
		game_name_error_msg = "Game name '{}' is unavaible".format(game_name) if c.fetchall() else None
		invalid_invitees = []
		for invitee in invitees:
			c.execute("""SELECT username FROM users WHERE username = %s;""", (invitee,))
			if not c.fetchone():
				invalid_invitees.append(invitee)
		invite_error_msg = None if not invalid_invitees else "Usernames '" + "', '".join(invalid_invitees) + "' do not exist"
		if game_name_error_msg or invite_error_msg:
			conn.close()
			return render_template("create_game.html", username = session.get("username"), game_name_error_msg = game_name_error_msg, invite_error_msg = invite_error_msg)
		else:
			invitees.add(session["username"])
			for invitee in invitees:
				c.execute("""INSERT INTO games (game_name, username, join_date) VALUES (%s, %s, CURRENT_TIMESTAMP);""", (game_name, invitee))
			conn.commit()
			conn.close()
			return redirect(url_for("user", username = session["username"]))
	elif not session.get("username"):
		return redirect(url_for("login"))
	else:
		return render_template("create_game.html", username = session.get("username"))













@app.route("/create_card")
def create_card(): ##add to database and session. On login, make sure to add all info to session as well. Think about what if already has info, etc...
	if session.get("username"):
		breeds = [BREEDS[random.randint(0, 3)] for _ in range(4)]
		conn = db_connect()
		c = conn.cursor()
		c.execute("DELETE FROM cards WHERE username = %s", (session["username"],))
		conn.commit()
		for i, breed in enumerate(breeds):
			c.execute("INSERT INTO cards VALUES (%s, %s, %s)", (session["username"], i, breed))
		conn.commit()

		c.execute("""SELECT filename from cards JOIN dogs 
			         ON cards.breed = dogs.breed 
			         WHERE username = %s 
			         ORDER BY slot""", (session["username"],))
		filenamess = [path.join("img", tup[0]) for tup in c.fetchall()]
		conn.close()
		session["breeds"] = breeds
		session["filenamess"] = filenamess
	return redirect(url_for("index"))


@app.route("/vidtest")
def vidtest():
	return render_template("vidtest.html")


@app.route("/test_upload", methods=["POST"])
def test_upload(): ## give infer image without saving?
	if request.method == "POST":
		raw_file = request.files["file"].read()
		probs = infer(consts.CURRENT_MODEL_NAME, raw_file)
		return render_template("game.html", username = session.get("username"), filenames = session.get("filenames"), display_probs = True, probs = probs.take(range(5)).values)




if __name__ == "__main__":
	port = int(environ.get("PORT", 5000))
	app.run(host="0.0.0.0", port=port, debug=True)
