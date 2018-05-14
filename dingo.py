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
## is preflighting slow? can i get around this? put stuff in forms and submit it from form?
##if a server error happens(4xx,5xx), does it include cors headers to get that back to client? or will it get a cors error? i think flask_cors fixes this..?
## RETURNING in SQL only for postgresql...

##every so often, check if there are games that no one is in, then delete squares, notifications or matches to gameplayer_ids that arent in game, delete those

app = Flask(__name__)
#CORS(app)
app.secret_key = urandom(24)


BREEDS = ["Golden Retriever", "English Setter", "Beagle", "Weimaraner"]
CARD_SIZE = 4
PASSING_PROB = 0.2 ## calibrate after getting rid of a bunch, especially those that cause easy confusion. find 10 high quality pictures and uplaod them and see if theres confusion. then try medium quality low quality. see what needs to happen, right now its too tight. perfect beagle gets .95 english foxhound. or instead of checking agianst a passing_prob, check that its in top 3. this might work well if its tight, but not well if there are less breeds? cus if a dog looks like no other dog, un-lookalike ones will get in top 3? #also, need to prevent random shots, or drawings? try cartoonish drawings like something that is just a crude outline and black spots. but prevent those from getting one. so if top 3 re all .3, .2, .2, then no. so it has to be in top 3 and about .3? or something. just test every breed. #with top 3 youll easily be able to fool. anything that looks like a beagle can pass. a bassett hound? try this(update: maybe its fine...).





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


#@app.route("/login", methods=["POST"])   ###NEW######
#def login():
#	username = request.form.get("username")
#	pw = request.form.get("password")
#	error_msg = validate_user(username, pw)
#	if error_msg == None:
#		return 'success'
#	else:
#		return error_msg













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








#####REACT######

















@app.route("/validate_breed", methods=["POST", "OPTIONS"]) ###use ajax... ?huh? //need to update backend database and push to everyone else... 
def validate_breed(): ## give infer image without saving?
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	raw_file = request.files['file'].read()
	print("$$$" + raw_file)
	print(type(raw_file))
	request_data = request.form
	submit_breed = request_data['breedName'].lower().replace(' ', '_') #or data?
	index = request_data['index']
	gpid = request_data['gpid']
	game_id = request_data['game_id']


	probs = infer(consts.CURRENT_MODEL_NAME, raw_file)
	top3 = probs.take([i for i in range(3)]).values.tolist()[:3]
	for i in range(3):####
		print(top3[i][0], top3[i][1]) ###
	response_data = {'match': False}
	for i in range(3):
		if top3[i][0] == submit_breed and top3[i][1] > PASSING_PROB:
			response_data['match'] = True

	response_data['match'] = True	 #####tempppppp for testing!!!


	if response_data['match'] == True:
		conn = db_connect()
		curs = conn.cursor()

		curs.execute("INSERT INTO matches (gameplayer_id, index) VALUES (%s, %s);""", (gpid, index))
		conn.commit()

		curs.execute("""INSERT INTO nots (gameplayer_id, notifier_id, type) SELECT gameplayer_id, %s, %s FROM gameplayers WHERE game_id = %s AND gameplayer_id != %s;""", (gpid, request_data['breedName'], game_id, gpid))
		conn.commit()

		conn.close()

	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response

#check if theres a bingo here, or on redirect to game?















@app.route("/homedata", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def homedata():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	my_user_id = request_data['user_id']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT first_name, last_name, email, img FROM users WHERE user_id = %s;""", (my_user_id,))
	conn.commit()
	my_data = curs.fetchone()

	my_profile = {'first_name': my_data[0], 'last_name': my_data[1], 'email': my_data[2], 'img': my_data[3], 'user_id': my_user_id}

	curs.execute("""SELECT gameplayer_id, game_id FROM gameplayers WHERE user_id = %s AND in_game = TRUE ORDER BY join_time;""", (my_user_id,))
	conn.commit()
	my_games = curs.fetchall()

	games_data = [get_game_data(game_id, my_gpid, curs, conn) for my_gpid, game_id in my_games]




	#get invitations
	curs.execute("""SELECT inv_id, first_name FROM invs INNER JOIN users ON invs.inviter_id = users.user_id WHERE invitee_id = %s ORDER BY sent_time;""", (my_user_id,))
	conn.commit()

	invs = [{'inv_id': inv_id, 'inviter_name': first_name} for inv_id, first_name in curs.fetchall()] 



	response_data = {}
	response_data['myProfile'] = my_profile
	response_data['games'] = games_data
	response_data['invs'] = invs



	conn.close()
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



@app.route("/new_game", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def new_game():
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
	curs.execute("""INSERT INTO gameplayers (game_id, user_id) VALUES (%s, %s) RETURNING gameplayer_id;""", (new_game_id, my_user_id))
	conn.commit()
	new_gpid = curs.fetchone()[0]



	#add squares for game
	curs.execute("""SELECT dog_id FROM dogs;""")
	conn.commit()
	all_dog_ids = curs.fetchall()
	random.shuffle(all_dog_ids)
	for index, dog_id in enumerate(all_dog_ids[:25]):
		curs.execute("""INSERT INTO squares (game_id, index, dog_id) VALUES (%s, %s, %s);""", (new_game_id, index, dog_id))
		conn.commit()		

	game_data = get_game_data(new_game_id, new_gpid, curs, conn)

	conn.close()

	response = jsonify(game_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



@app.route("/invite", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def invite():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	inviter_id = request_data['inviter_id']
	invitee_id = request_data['invitee_id']
	game_id = request_data['game_id']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""INSERT INTO invs (invitee_id, game_id, inviter_id) VALUES (%s, %s, %s);""", (invitee_id, game_id, inviter_id))
	conn.commit()

	response = Response()
	response.headers['Access-Control-Allow-Origin'] = "*"
	return response



@app.route("/accept_invite", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def accept_invite():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	inv_id = request_data['inv_id']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""DELETE FROM invs WHERE inv_id = %s RETURNING game_id, invitee_id;""", (inv_id,)) #delete all inviations to that
	conn.commit()
	game_id, user_id = curs.fetchone()

	curs.execute("""INSERT INTO gameplayers (game_id, user_id) VALUES (%s, %s) RETURNING gameplayer_id;""", (game_id, user_id))
	conn.commit()
	new_gpid = curs.fetchone()[0]

	game_data = get_game_data(game_id, new_gpid, curs, conn)

	curs.execute("""INSERT INTO nots (gameplayer_id, notifier_id, type) SELECT gameplayer_id, %s, %s FROM gameplayers WHERE game_id = %s AND in_game = TRUE AND gameplayer_id != %s;""", (new_gpid, 'join', game_id, new_gpid))
	conn.commit()

	conn.close()

	response = jsonify(game_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response


@app.route("/delete_invite", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def delete_invite():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	inv_id = request_data['inv_id']
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""DELETE FROM invs WHERE inv_id = %s;""", (inv_id,))
	conn.commit()

	conn.close()

	response = Response()
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response







@app.route("/get_top_players", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def get_top_players():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	user_id = request_data['user_id']
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT users.user_id, users.first_name, users.last_name, users.img FROM gameplayers AS gp1 INNER JOIN gameplayers AS gp2 ON gp1.game_id = gp2.game_id INNER JOIN users ON gp2.user_id = users.user_id WHERE gp1.user_id = %s AND gp2.user_id != %s GROUP BY users.user_id, users.first_name, users.last_name, users.img ORDER BY COUNT(users.user_id);""", (user_id, user_id))
	conn.commit()

	top_players = [{'user_id': row[0], 'first_name': row[1], 'last_name': row[2], 'img': row[3]} for row in curs.fetchall()]

	conn.close()

	response = jsonify(top_players)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



@app.route("/search_players", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def search_players():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	patterns = request_data['pattern'].strip().split()
	first_pattern = patterns[0]
	last_pattern =  patterns[1] if len(patterns) > 1 else ''
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT user_id, first_name, last_name, img FROM users WHERE (first_name LIKE %s AND last_name LIKE %s) OR (first_name LIKE %s AND last_name LIKE %s) LIMIT 30;""", (first_pattern + '%', last_pattern + '%', last_pattern + '%', first_pattern + '%'))
	conn.commit()

	results = [{'user_id': row[0], 'first_name': row[1], 'last_name': row[2], 'img': row[3]} for row in curs.fetchall()]

	conn.close()

	response = jsonify(results)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response


@app.route("/leave_game", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def leave_game():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	gpid = request_data['gpid']
	game_id = request_data['game_id']
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""UPDATE gameplayers SET in_game = FALSE WHERE gameplayer_id = %s;""", (gpid,))
	conn.commit()

	curs.execute("""INSERT INTO nots (gameplayer_id, notifier_id, type) SELECT gameplayer_id, %s, %s FROM gameplayers WHERE game_id = %s AND gameplayer_id != %s;""", (gpid, 'leave', game_id, gpid))
	conn.commit()

	conn.close()

	response = Response()
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



@app.route("/read_nots", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def read_nots():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	not_ids = request_data['read_nots']
	
	conn = db_connect()
	curs = conn.cursor()

	for id in not_ids:
		curs.execute("""UPDATE nots SET read = TRUE WHERE not_id = %s;""", (id,))
		conn.commit()

	conn.close()

	response = Response()
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response








@app.route("/update_profile", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def update_profile():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	first_name = request_data.get('first_name')
	last_name = request_data.get('last_name')
	email = request_data.get('email')
	img = request_data.get('img')
	user_id = request_data.get("user_id")
	
	conn = db_connect()
	curs = conn.cursor()

	response_data = {}

	if email:
		print(email)
		curs.execute("""SELECT email from users WHERE email=%s;""", (email,))
		conn.commit()
		if curs.rowcount > 0:
			response_data['error_msg'] = "Email Address {} has already been used".format(email)
		else:
			curs.execute("""UPDATE users SET email = %s WHERE user_id = %s;""", (email, user_id))
			conn.commit()

	if first_name and not response_data.get('error_msg'):
		print(first_name)
		curs.execute("""UPDATE users SET first_name = %s WHERE user_id = %s;""", (first_name, user_id))
		conn.commit()
	if last_name and not response_data.get('error_msg'):
		print(last_name)
		curs.execute("""UPDATE users SET last_name = %s WHERE user_id = %s;""", (last_name, user_id))
		conn.commit()
	if img and not response_data.get('error_msg'):
		print(img)
		curs.execute("""UPDATE users SET img = %s WHERE user_id = %s;""", (img, user_id))
		conn.commit()

	conn.close()

	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



##gets game data for game id, if gpid is present than its a game im in, other wise not. assume it is there for now... curs in here for now, but eventually make a class that stores it and has different methods that can use it
def get_game_data(game_id, gpid, curs, conn):
	game_data = {}
	print(gpid)


	game_data['game_id'] = game_id
	print(gpid)
##put get breeds..., get players... etc in their own functions
	curs.execute("""SELECT breed_name, img FROM squares INNER JOIN dogs ON squares.dog_id = dogs.dog_id WHERE game_id = %s ORDER BY index;""", (game_id,))
	conn.commit()
	game_data['squares'] = [{'breed_name': breed_name, 'img': img} for breed_name, img in curs.fetchall()]
	print(gpid)

	curs.execute("""SELECT gameplayer_id, first_name, img FROM gameplayers INNER JOIN users ON gameplayers.user_id = users.user_id WHERE game_id = %s AND in_game = TRUE ORDER BY gameplayers.join_time;""", (game_id,))
	conn.commit()
	print(gpid)
	players = [{'gpid': row[0], 'first_name': row[1], 'img': row[2]} for row in curs.fetchall()]
	for i in range(len(players)):
		if players[i]['gpid'] == gpid:
			players.insert(0, players.pop(i))
	game_data['players'] = players

	print(gpid)
	curs.execute("""SELECT matches.gameplayer_id, index FROM gameplayers INNER JOIN matches ON gameplayers.gameplayer_id = matches.gameplayer_id WHERE game_id = %s;""", (game_id,))
	conn.commit()
	matches = defaultdict(list)
	for gp_id, index in curs.fetchall():
		matches[gp_id].append(index)
	for player in game_data['players']:
		player['matches'] = matches[player['gpid']]

	print(gpid)


	#nots...
	print(gpid)
	curs.execute("""SELECT not_id, notifier_id, first_name, img, type, read FROM nots INNER JOIN gameplayers ON nots.notifier_id = gameplayers.gameplayer_id  INNER JOIN users ON gameplayers.user_id = users.user_id WHERE nots.gameplayer_id = %s ORDER BY sent_time;""", (gpid,))
	conn.commit()

	game_data['nots'] = list(map(format_nots, curs.fetchall())) ##

	return game_data


def format_nots(row):
	notification = {}
	notification['not_id'] = row[0]
	notification['read'] = row[5]
	notifier = {}
	notifier['gpid'] = row[1]
	notifier['first_name'] = row[2]
	notifier['img'] = row[3]
	notification['notifier'] = notifier
	type = row[4]
	if type == 'join':
		notification['msg'] = "{} has joined the game".format(row[2])
	elif type == 'leave':
		notification['msg'] = "{} has left the game".format(row[2])
	else:
		notification['msg'] = "{} has found a {}".format(row[2], type)
	return notification







































































































@app.route("/validate_signup", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def validate_signup():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	first = request_data['firstName']
	last = request_data['lastName']
	pw = request_data['password']
	confirm_pw = request_data['confirmPassword']
	email = request_data['email']

	response_data = {}

	if '' in request_data.values():
		response_data['errorMsg'] = "Fields cannot be empty"
	elif len(pw) < 8:
		response_data['errorMsg'] = "Password must be at least 8 characters"
	elif pw != confirm_pw:
		response_data['errorMsg'] = "Passwords do not match"

	if 'errorMsg' in response_data:
		response = jsonify(response_data)
		response.headers['Access-Control-Allow-Origin'] = '*'
		return response
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT email FROM users WHERE email = %s;""", (email,))
	conn.commit()
	if curs.rowcount > 0:
		response_data['errorMsg'] = 'Email address {} has already been used'.format(email)

	conn.close()
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response















@app.route("/signup", methods=["POST", "OPTIONS"])   #need to only put in lowercase data..
def signup():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json() ##make cleaner? like javascript decompose?
	email = request_data.get('email')
	first = request_data.get('firstName')
	last = request_data.get('lastName')
	pw = request_data.get("password")
	img = request_data.get("img")

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""INSERT INTO users (first, last, pw, email, img) VALUES (LOWER(%s), LOWER(%s), %s, LOWER(%s), %s) RETURNING u_id;""", (first, last, generate_password_hash(pw), email, img))
	conn.commit()
	u_id = curs.fetchone()[0]
	response_data = {}
	response_data['userId'] = u_id

	conn.close()
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response
















@app.route("/login", methods=["POST", "OPTIONS"])   
def login():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	email = request_data.get('email')
	pw = request_data.get("password")

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT email, pw, u_id FROM users WHERE email = %s;""", (email,))
	conn.commit()
	result = curs.fetchone();
	response_data = {}
	if curs.rowcount == 0:
		response_data['success'] = False
		response_data['errorMsg'] = "Email Address {} does not exist".format(email)
	elif not check_password_hash(result[1], pw):
		response_data['success'] = False
		response_data['errorMsg'] = "Incorrect password"
	else:
		response_data['success'] = True
		response_data['userId'] = result[2]

	conn.close()
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response






























@app.route("/all_data", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def all_data():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	u_id = request_data['userId']

	conn = db_connect() ##make these available in helper functions
	curs = conn.cursor()

	invs = []
	all_profs = {}
	games = []
	players = {}
	matches = {}
	nots = {}

	g_ids = get_g_ids(u_id, curs, conn)
	for g_id in g_ids:
		game_squares = get_squares(g_id, curs, conn)
		game_matches = get_matches(g_id, curs, conn)
		game_players, game_player_profs = get_players(g_id, u_id, curs, conn)
		game_nots, game_nots_profs = get_nots(g_id, u_id, curs, conn)

		games.append({'gameId': g_id, 'squares': game_squares})
		matches[g_id] = game_matches
		players[g_id] = game_players
		nots[g_id] = game_nots
		all_profs.update(game_player_profs)
		all_profs.update(game_nots_profs)

	invs, invs_profs = get_invs(u_id, curs, conn)
	my_prof = get_my_prof(u_id, curs, conn)

	all_profs.update(invs_profs)
	all_profs.update(my_prof)
	#top_players_profs? or localstorage?

	response_data = {}
	response_data['games'] = games
	response_data['invs'] = invs
	response_data['nots'] = nots
	response_data['players'] = players
	response_data['matches'] = matches
	response_data['allProfs'] = all_profs


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
	u_id = request_data['userId']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""INSERT INTO games (g_id) VALUES (DEFAULT) RETURNING g_id;""")
	conn.commit()
	g_id = curs.fetchone()[0]

	curs.execute("""INSERT INTO gameplayers (g_id, u_id) VALUES (%s, %s);""", (g_id, u_id))
	conn.commit()

	#add squares for game
	curs.execute("""SELECT dog_id FROM dogs;""")
	conn.commit()
	all_dog_ids = curs.fetchall()
	random.shuffle(all_dog_ids)

	for index, dog_id in enumerate(all_dog_ids[:25]):
		curs.execute("""INSERT INTO squares (g_id, index, dog_id) VALUES (%s, %s, %s);""", (g_id, index, dog_id))
		conn.commit()

	response_data = {}
	response_data['gameId'] = g_id
	response_data['squares'] = get_squares(g_id, curs, conn)
	response_data['players'] = [u_id]
	response_data['nots'] = []
	reponse_data['matches'] = {u_id: []}

	conn.close()

	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response















def get_my_prof(u_id, curs, conn):
	curs.execute("""SELECT first, last, email, img FROM users WHERE u_id = %s;""", (u_id,))
	conn.commit()
	first, last, email, img = curs.fetchone()

	my_prof = {u_id: {'firstName': first, 'lastName': last, 'email': email, 'img': img}}
	return my_prof




def get_invs(u_id, curs, conn):
	curs.execute("""SELECT inv_id, u_id, first, last, img FROM invs INNER JOIN users ON invs.from_id = users.u_id WHERE to_id = %s ORDER BY sent_time DESC;""", (u_id,))
	conn.commit()
	rows = curs.fetchall()

	invs = []
	profs = {}
	for row in rows:
		inv_id, from_id, first, last, img = row
		inv = {'invId': inv_id, 'fromId': from_id}
		invs.append(inv)
		if from_id not in profs:
			profs[from_id] = {'firstName': first, 'lastName': last, 'img': img}

	return invs, profs


def get_g_ids(u_id, curs, conn):
	curs.execute("""SELECT g_id FROM gameplayers WHERE u_id = %s ORDER BY join_time""", (u_id,))
	conn.commit()
	g_ids = [row[0] for row in curs.fetchall()]
	return g_ids


def get_squares(g_id, curs, conn):
	###EVENTUALLY JUST MOVE DOGS DATABASE TO LOCALSTORAGE?
	curs.execute("""SELECT breed, img FROM squares INNER JOIN dogs ON squares.dog_id = dogs.dog_id WHERE squares.g_id = %s ORDER BY index ASC;""", (g_id,))
	conn.commit()
	rows = curs.fetchall()

	squares = [{'breed': breed, 'img': img} for breed, img in rows]

	return squares


def get_nots(g_id, u_id, curs, conn):
	curs.execute("""SELECT not_id, from_id, type, first, last, img FROM nots INNER JOIN users ON from_id = u_id WHERE to_id = %s AND g_id = %s ORDER BY sent_time DESC;""", (u_id, g_id))
	conn.commit()
	rows = curs.fetchall()

	nots = []
	profs = {}
	for not_id, from_id, type, first, last, img in rows:
		nots.append({'notId': not_id, 'fromId': from_id, 'type': type})
		if from_id not in profs:
			profs[from_id] = {'firstName': first, 'lastName': last, 'img': img}

	return nots, profs


def get_players(g_id, u_id, curs, conn):
	curs.execute("""SELECT users.u_id, first, last, img FROM gameplayers INNER JOIN users ON gameplayers.u_id = users.u_id WHERE g_id = %s ORDER BY join_time;""", (g_id,))
	conn.commit()
	rows = curs.fetchall()

	players = []
	profs = {}
	for player_id, first, last, img in rows:
		players.append(player_id)
		if player_id not in profs:
			profs[player_id] = {'firstName': first, 'lastName': last, 'img': img}

	players.insert(0, players.pop(players.index(u_id)))

	return players, profs


def get_matches(g_id, curs, conn):
	curs.execute("""SELECT u_id, index FROM matches WHERE g_id = %s;""", (g_id,))
	conn.commit()
	rows = curs.fetchall()

	matches = defaultdict(list)
	for u_id, index in rows:
		matches[u_id].append(index)

	return matches



if __name__ == "__main__":
	port = int(environ.get("PORT", 5000))
	app.run(host="0.0.0.0", port=port, debug=True)
