from collections import defaultdict
from flask import Flask, flash, request, session, render_template, redirect, url_for, send_from_directory, jsonify, Response
from psycopg2 import connect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from os import urandom, path, environ
import random ##
import json
from breed_classifier.inference.classify import infer
from breed_classifier.common import consts
from urllib import parse
from sys import argv
from flask_cors import CORS ##need this? uninstall? deal with preflighting manually to set allow-origin? this is safer?


###everything needs to get redirected if not logged in etc.
### 	response.headers['Access-Control-Allow-Origin'] = '*'   look into these... (put origin: [app domain] in request then replace * with [app domain])
## is preflighting slow? can i get around this?
##if a server error happens(4xx,5xx), does it include cors headers to get that back to client? or will it get a cors error? i think flask_cors fixes this..?
## RETURNING in SQL only for postgresql...

app = Flask(__name__)
#CORS(app)
app.secret_key = urandom(24)


BREEDS = ["Golden Retriever", "English Setter", "Beagle", "Weimaraner"]
CARD_SIZE = 4
PASSING_PROB = 0.8 ## calibrate after getting rid of a bunch, especially those that cause easy confusion. find 10 high quality pictures and uplaod them and see if theres confusion. then try medium quality low quality. see what needs to happen, right now its too tight. perfect beagle gets .95 english foxhound. or instead of checking agianst a passing_prob, check that its in top 3. this might work well if its tight, but not well if there are less breeds? cus if a dog looks like no other dog, un-lookalike ones will get in top 3? #also, need to prevent random shots, or drawings? try cartoonish drawings like something that is just a crude outline and black spots. but prevent those from getting one. so if top 3 re all .3, .2, .2, then no. so it has to be in top 3 and about .3? or something. just test every breed. #with top 3 youll easily be able to fool. anything that looks like a beagle can pass. a bassett hound? try this(update: maybe its fine...).





#######
def db_connect():
	if len(argv) == 2: #for testing
		conn = connect("dbname=dingo")
	else:
		parse.uses_netloc.append("postgres")
		url = parse.urlparse(environ["DATABASE_URL"])
		conn = connect(
			database=url.path[1:],
			user=url.username,
			password=url.password,
			host=url.hostname,
			port=url.port
		)
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




# @app.route("/", methods=["GET", "POST"])
# def login():
# 	if request.method == "POST":
# 		username = request.form.get("username")
# 		pw = request.form.get("password")
# 		error_msg = validate_user(username, pw)
# 		if error_msg == None:
# 			session["username"] = username
# 			return redirect(url_for('user', username = username))
# 		else:
# 			return render_template("login.html", error_msg = error_msg)
# 	else:
# 		if "username" in session:
# 			return redirect(url_for('user', username = session["username"]))
# 		else:
# 			return render_template("login.html")


@app.route("/login", methods=["POST"])   ###NEW######
def login():
	username = request.form.get("username")
	pw = request.form.get("password")
	error_msg = validate_user(username, pw)
	if error_msg == None:
		return 'success'
	else:
		return error_msg













######################
######################








# @app.route("/logout")
# def logout():
# 	session.clear()
# 	return redirect(url_for('login'))



@app.route("/user/<username>")
def user(username):
	if username != session.get("username"):
		return redirect(url_for('login'))
	conn = db_connect()
	c = conn.cursor()

	c.execute("""SELECT game_name FROM games
		         WHERE username = %s 
		         ORDER BY join_date""", (username,))
	game_names = [match[0] for match in c.fetchall()]

	c.execute("""SELECT friend, status FROM friends
		         WHERE username = %s 
		         ORDER BY friend ASC""", (username,))
	matches = c.fetchall() 
	friends = [match[0] for match in matches if match[1] == "confirmed"]
	pending_requests = [match[0] for match in matches if match[1] == "pending"]
	print(pending_requests)
	conn.close()

	return render_template("user.html", username=username, game_names=game_names, friends=friends, pending_requests=pending_requests)


@app.route("/user/<username>/<game_name>") #check that slots are in right order 
def game(username, game_name):
	if username != session.get("username"):
		return redirect(url_for('login'))

	conn = db_connect()
	c = conn.cursor()
	c.execute("""SELECT slot, cards.breed, filename, checked FROM cards, dogs WHERE cards.breed = dogs.breed AND cards.username = %s AND cards.game_name = %s ORDER BY slot ASC""", (username, game_name))
	card = c.fetchall()
	conn.close()
	return render_template("game.html", card=card, username=username, game_name=game_name)






@app.route("/create_game", methods=["GET", "POST"]) #games of same name???
def create_game(): #can't invite yourself
	if request.method == "POST":
		game_name = request.form["game_name"]
		if not game_name:
			return render_template("create_game.html", username=session.get("username"), game_name_error_msg="Game name cannot be empty")
		invitees = {invitee.strip() for invitee in request.form["invitees"].split(",") if invitee}
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
			return render_template("create_game.html", username=session.get("username"), game_name_error_msg=game_name_error_msg, invite_error_msg=invite_error_msg)
		else:
			invitees.add(session["username"])
			for invitee in invitees:
				c.execute("""INSERT INTO games (game_name, username, join_date) VALUES (%s, %s, CURRENT_TIMESTAMP);""", (game_name, invitee))
			conn.commit()
			conn.close()
			return redirect(url_for("user", username=session["username"]))
	elif not session.get("username"):
		return redirect(url_for("login"))
	else:
		return render_template("create_game.html", username=session.get("username"))











@app.route("/create_card/<game_name>") # only post? yes. 
def create_card(game_name):
	username = session.get("username")
	if username:
		#delete old card
		conn = db_connect()
		c = conn.cursor()
		c.execute("DELETE FROM cards WHERE username = %s and game_name = %s", (username, game_name))
		conn.commit()

		c.execute("SELECT breed FROM dogs")
		all_breeds = c.fetchall()
		breed_cnt = len(all_breeds)

		for i in range(CARD_SIZE):
			breed_choice = all_breeds[random.randint(0, breed_cnt - 1)]
			c.execute("INSERT INTO cards (username, game_name, slot, breed) VALUES (%s, %s, %s, %s)", (username, game_name, i, breed_choice))
		conn.commit()
		conn.close()
		return redirect(url_for("game", username=username, game_name=game_name))
	else:
		redirect(url_for("login"))






@app.route("/test_upload", methods=["POST"]) ###use ajax...
def test_upload(): ## give infer image without saving?
	if request.method == "POST":
		username = request.form['username']
		game_name = request.form['game_name']
		raw_file = request.files["file"].read()
		probs = infer(consts.CURRENT_MODEL_NAME, raw_file)
		submit_breed = request.form['breed'].lower().replace(' ', '_')
		for i in range(5):
			temp, tempp = probs.take([i]).values.tolist()[0]
			print(temp, tempp)
		guess_breed, guess_prob = probs.take([0]).values.tolist()[0]
		print(guess_prob, guess_breed)
		if guess_breed == submit_breed and guess_prob > PASSING_PROB:
			slot = request.form['slot']
			conn = db_connect()
			c = conn.cursor()
			c.execute("UPDATE cards SET checked=TRUE WHERE username = %s AND game_name = %s AND slot = %s", (username, game_name, slot))
			conn.commit()
			conn.close()
			#check if theres a bingo here, or on redirect to game?
		else:
			pass #let them know it failed...
		return redirect(url_for("game", username=username, game_name=game_name))


@app.route("/friend_request", methods=["GET", "POST"])  ##check on all things that there is a check for username in session, etc..
def friend_request(): #can't invite yourself. # cant send request to someone who is waiting for a response from you.
	username = session.get("username")
	if request.method == "POST":
		requestees = {requestee.strip() for requestee in request.form["requestees"].split(",") if requestee}
		conn = db_connect()
		c = conn.cursor()

		request_error_msg = None
		invalid_requestees = []
		for requestee in requestees:
			c.execute("""SELECT username FROM users WHERE username = %s;""", (requestee,))
			if not c.fetchone():
				invalid_requestees.append(requestee)
		if invalid_requestees:
			request_error_msg = "Usernames '" + "', '".join(invalid_requestees) + "' do not exist"
		else:
			for requestee in requestees:
				c.execute("""SELECT * FROM friends WHERE username = %s AND friend = %s;""", (username, requestee,))
				if c.fetchone():
					invalid_requestees.append(requestee)
			if invalid_requestees:
				request_error_msg = "You are already friend with or have a pending request with '" + "', '".join(invalid_requestees) + "'"


		if request_error_msg:
			conn.close()
			return render_template("friend_request.html", username=username, request_error_msg=request_error_msg)
		else:
			for requestee in requestees:
				c.execute("""INSERT INTO friends (username, friend, status) VALUES (%s, %s, 'pending');""", (requestee, username))
			conn.commit()
			conn.close()
			return redirect(url_for("user", username=username))

	elif not username:
		return redirect(url_for("login"))
	else:
		return render_template("friend_request.html", username=username)



@app.route("/handle_request/<requester>/<confirm>", methods=["GET"]) #get? make things post that can be post...
def handle_request(requester, confirm):
	username = session.get("username")
	if not username:
		return redirect(url_for("login"))
	conn = db_connect()
	c = conn.cursor()

	if confirm == "True": #uhhh 
		c.execute("""UPDATE friends SET status = 'confirmed' WHERE username = %s AND friend = %s;""", (username, requester))
		c.execute("""INSERT INTO friends(username, friend, status) VALUES (%s, %s, 'confirmed');""", (requester, username))
	else:
		c.execute("""DELETE FROM friends WHERE username = %s AND friend = %s;""", (username, requester))
	conn.commit()
	conn.close()
	return redirect(url_for('user', username=username))


























@app.route("/validate_breed", methods=["POST"]) ###use ajax... ?huh? //need to update backend database and push to everyone else... 
def validate_breed(): ## give infer image without saving?
	raw_file = request.files['file'].read()
	submit_breed = request.form['breedName'].lower().replace(' ', '_') #or data?
	probs = infer(consts.CURRENT_MODEL_NAME, raw_file)
	top3 = probs.take([i for i in range(3)]).values.tolist()[:3]
	for i in range(3):####
		print(top3[i][0], top3[i][1]) ###
	response_data = {'match': False}
	for i in range(3):
		if top3[i][0] == submit_breed and top3[i][1] > PASSING_PROB:
			response['match'] = True
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response
#		if guess_breed == submit_breed and guess_prob > PASSING_PROB:
#			slot = request.form['slot']
#			conn = db_connect()
#			c = conn.cursor()
#			c.execute("UPDATE cards SET checked=TRUE WHERE username = %s AND game_name = %s AND slot = %s", (username, game_name, slot))
#			conn.commit()
#			conn.close()
		#check if theres a bingo here, or on redirect to game?
#		else:
#			pass #let them know it failed...
#		return redirect(url_for("game", username=username, game_name=game_name))



#####REACT######



@app.route("/signup", methods=["POST", "OPTIONS"])   
def signup():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	email = request_data.get('emailAddress')
	first_name = request_data.get('firstName')
	last_name = request_data.get('lastName')
	pw = request_data.get("password")

	if email == "error":  #####
		return Response(status=401, headers={'Access-Control-Allow-Origin': '*'}) ####

	conn = db_connect()
	curs = conn.cursor()

	#check if email already exist
	curs.execute("""SELECT email FROM users WHERE email = %s;""", (email,))
	response_data = {}
	if curs.rowcount > 0:
		response_data['success'] = False
		response_data['error_msg'] = "Email Address {} already exists".format(email)
	else:
		curs.execute("""INSERT INTO users (first_name, last_name, password, email) VALUES (%s, %s, %s, %s) RETURNING user_id;""", (first_name, last_name, generate_password_hash(pw), email))
		conn.commit()
		new_user_id = curs.fetchone()[0]
		response_data['success'] = True
		response_data['user_id'] = new_user_id
	conn.close()
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response


@app.route("/homedata", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def homedata():
	print(1)
	if request.method == "OPTIONS":
		print(2)
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response
		print(3)
	request_data = request.get_json()
	my_user_id = request_data['user_id']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT gameplayer_id, game_id FROM gameplayers WHERE user_id = %s ORDER BY join_time;""", (my_user_id,))
	conn.commit()
	my_games = curs.fetchall()
	print(4)
	games_data = []
	for my_gpid, game_id in my_games:
		game_data = {}


		game_data['game_id'] = game_id

##put in function...
		curs.execute("""SELECT squares.dog_id, breed_name, img FROM squares INNER JOIN dogs ON squares.dog_id = dogs.dog_id WHERE game_id = %s ORDER BY index;""", (game_id,))
		conn.commit()
		game_data['squares'] = [{'dog_id': dog_id, 'breed_name': breed_name, 'img': img} for dog_id, breed_name, img in curs.fetchall()]


		curs.execute("""SELECT gameplayer_id, first_name, img FROM gameplayers INNER JOIN users ON gameplayers.user_id = users.user_id WHERE game_id = %s ORDER BY gameplayers.join_time;""", (game_id,))
		conn.commit()

		players = [{'gpid': row[0], 'first_name': row[1], 'img': row[2]} for row in curs.fetchall()]
		for i in range(len(players)):
			if players[i]['gpid'] == my_gpid:
				players.insert(0, players.pop(i))
		game_data['players'] = players


		curs.execute("""SELECT matches.gameplayer_id, index FROM gameplayers INNER JOIN matches ON gameplayers.gameplayer_id = matches.gameplayer_id WHERE game_id = %s;""", (game_id,))
		conn.commit()
		matches = defaultdict(list)
		for gpid, index in curs.fetchall():
			matches[gpid].append(index)
		for player in game_data['players']:
			player['matches'] = matches[player['gpid']]




		#notifications...
		game_data['notifications'] = []


		games_data.append(game_data)



	#get invitations
	invitations = []



	response_data = {}
	response_data['games'] = games_data
	response_data['invitations'] = invitations

	##game_data looks like...
	# {
	#game_id: 323
	#squares: [{dog_id:  , breed_name:   , index:    img:   }, {...}, ...]
	#notifications: [FIGURE THIS OUT!]
	#players: [{gpid:   ,  first_name:    ,   img:       ,  matches: [] }]
	#me: {}
	#} 

	conn.close()
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



@app.route("/newgame", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def newgame():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	my_user_id = request_data['user_id']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""INSERT INTO games (game_id) VALUES (DEFAULT) RETURNING game_id;""")
	conn.commit()
	new_game_id = curs.fetchone()[0]
	curs.execute("""INSERT INTO gameplayers (gameplayer_id, game_id, user_id) VALUES (DEFAULT, %s, %s) RETURNING gameplayer_id;""", (new_game_id, my_user_id))
	conn.commit()
	new_gpid = curs.fetchone()[0]



	#add squares for game!!!
	curs.execute("""SELECT dog_id, breed_name, img FROM dogs;""")
	conn.commit()
	all_dogs = curs.fetchall()
	random.shuffle(all_dogs)
	squares = [{'index': index, 'dog_id': row[0],'breed_name': row[1], 'img': row[2]} for index, row in enumerate(all_dogs[:25])]
	for square in squares:
		curs.execute("""INSERT INTO squares (game_id, index, dog_id) VALUES (%s, %s, %s);""", (new_game_id, square['index'], square['dog_id']))
		conn.commit()

	curs.execute("""SELECT first_name, img FROM users WHERE user_id = %s;""", (my_user_id,))
	conn.commit()
	first_name, img = curs.fetchone()
	conn.close()

	me = {}
	me['gpid'] = new_gpid
	me['first_name'] = first_name
	me['img'] = img
	me['matches'] = []

	response_data = {}
	response_data['game_id'] = new_game_id
	response_data['squares'] = squares
	response_data['notifications'] = []
	response_data['players'] = [me]
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response




if __name__ == "__main__":
	port = int(environ.get("PORT", 5000))
	app.run(host="0.0.0.0", port=port, debug=True)
