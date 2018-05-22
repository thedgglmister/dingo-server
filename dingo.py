from collections import defaultdict
from flask import Flask, request, jsonify, Response
from psycopg2 import connect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename #?
from os import urandom, path, environ #?
import random ##
import json
import base64
from breed_classifier.inference.classify import infer
from breed_classifier.common import consts
from urllib import parse #?
from sys import argv
from flask_cors import CORS ##need this? uninstall? deal with preflighting manually to set allow-origin? this is safer?


### 	response.headers['Access-Control-Allow-Origin'] = '*'   look into these... (put origin: [app domain] in request then replace * with [app domain])
## is preflighting slow? can i get around this? put stuff in forms and submit it from form?
##if a server error happens(4xx,5xx), does it include cors headers to get that back to client? or will it get a cors error? i think flask_cors fixes this..?
## RETURNING in SQL only for postgresql...

##every so often, check if there are games that no one is in, then delete squares, notifications or matches to gameplayer_ids that arent in game, delete those

app = Flask(__name__)
#CORS(app)
app.secret_key = urandom(24)




PASSING_PROB = 0.2 ## calibrate after getting rid of a bunch, especially those that cause easy confusion. find 10 high quality pictures and uplaod them and see if theres confusion. then try medium quality low quality. see what needs to happen, right now its too tight. perfect beagle gets .95 english foxhound. or instead of checking agianst a passing_prob, check that its in top 3. this might work well if its tight, but not well if there are less breeds? cus if a dog looks like no other dog, un-lookalike ones will get in top 3? #also, need to prevent random shots, or drawings? try cartoonish drawings like something that is just a crude outline and black spots. but prevent those from getting one. so if top 3 re all .3, .2, .2, then no. so it has to be in top 3 and about .3? or something. just test every breed. #with top 3 youll easily be able to fool. anything that looks like a beagle can pass. a bassett hound? try this(update: maybe its fine...).





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













@app.route("/validate_signup", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def validate_signup():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	first = request_data['firstName'].title()
	last = request_data['lastName'].title()
	pw = request_data['password']
	confirm_pw = request_data['confirmPassword']
	email = request_data['email'].lower()

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
	email = request_data.get('email').lower()
	first = request_data.get('firstName').title()
	last = request_data.get('lastName').title()
	pw = request_data.get("password")
	img = request_data.get("img")

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""INSERT INTO users (first, last, pw, email, img) VALUES (%s, %s, %s, %s, %s) RETURNING u_id;""", (first, last, generate_password_hash(pw), email, img))
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
	email = request_data.get('email').lower()
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
		game_players, game_player_profs = get_players(g_id, u_id, curs, conn)
		game_matches = get_matches(g_id, game_players, curs, conn)
		game_nots, game_nots_profs = get_nots(g_id, u_id, curs, conn)

		games.append({'gameId': g_id, 'squares': game_squares})
		matches[g_id] = game_matches
		players[g_id] = game_players
		nots[g_id] = game_nots
		all_profs.update(game_player_profs)
		all_profs.update(game_nots_profs)

	invs, invs_profs = get_invs(u_id, curs, conn)
	top_players, top_player_profs = get_top_players(u_id, curs, conn)
	my_prof = get_my_prof(u_id, curs, conn)

	all_profs.update(invs_profs)
	all_profs.update(top_player_profs)
	all_profs.update(my_prof)

	response_data = {}
	response_data['games'] = games
	response_data['invs'] = invs
	response_data['nots'] = nots
	response_data['players'] = players
	response_data['matches'] = matches
	response_data['topPlayers'] = top_players
	response_data['allProfs'] = all_profs



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
	response_data['games'] = [{'gameId': g_id, 'squares': get_squares(g_id, curs, conn)}]
	response_data['players'] = {g_id: [u_id]}
	response_data['nots'] = {g_id: []}
	response_data['matches'] = {g_id: {u_id: []}}

	conn.close()

	response = jsonify(response_data)
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
	u_id = request_data['userId']
	g_id = request_data['gameId']
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""UPDATE gameplayers SET in_game = FALSE WHERE g_id = %s AND u_id = %s;""", (g_id, u_id))
	conn.commit()

	curs.execute("""INSERT INTO nots (g_id, from_id, to_id, type) SELECT %s, %s, u_id, 'leave' FROM gameplayers WHERE g_id = %s AND in_game = TRUE AND u_id != %s;""", (g_id, u_id, g_id, u_id))
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
	first = request_data.get('firstName').title()
	last = request_data.get('lastName').title()
	email = request_data.get('email').lower()
	img = request_data.get('img')
	u_id = request_data.get("userId")
	
	conn = db_connect()
	curs = conn.cursor()

	response_data = {}

	if '' in request_data.values():
		response_data['errorMsg'] = 'Fields cannot be empty'
		response = jsonify(response_data)
		response.headers['Access-Control-Allow-Origin'] = '*'
		return response

	curs.execute("""SELECT email, u_id from users WHERE email = %s AND u_id != %s;""", (email, u_id))
	conn.commit()
	if curs.rowcount > 0:
		conn.close()
		response_data['errorMsg'] = "Email address {} has already been used".format(email)
		response = jsonify(response_data)
		response.headers['Access-Control-Allow-Origin'] = '*'
		return response

	curs.execute("""UPDATE users SET first = %s, last = %s, email = %s, img = %s WHERE u_id = %s;""", (first, last, email, img, u_id))
	conn.commit()

	conn.close()

	response_data['firstName'] = first
	response_data['lastName'] = last
	response_data['email'] = email
	response_data['img'] = img
	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



















@app.route("/accept_invite", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def accept_invite():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	inv_id = request_data['invId']

	conn = db_connect()
	curs = conn.cursor()
##high coding here
	curs.execute("""DELETE FROM invs WHERE g_id = (SELECT g_id FROM invs WHERE inv_id = %s) RETURNING g_id, to_id;""", (inv_id,))
	conn.commit()
	g_id, u_id = curs.fetchone()

	curs.execute("""INSERT INTO nots (to_id, from_id, type, g_id) SELECT u_id, %s, 'join', %s FROM gameplayers WHERE g_id = %s AND in_game = TRUE;""", (u_id, g_id, g_id))
	conn.commit()

	curs.execute("""INSERT INTO gameplayers (g_id, u_id) VALUES (%s, %s);""", (g_id, u_id))
	conn.commit()

	game_squares = get_squares(g_id, curs, conn)
	game_players, game_player_profs = get_players(g_id, u_id, curs, conn)
	game_matches = get_matches(g_id, game_players, curs, conn)
	top_players, top_player_profs = get_top_players(u_id, curs, conn)
	invs = get_invs(u_id, curs, conn)[0]

	response_data = {}
	response_data['games'] = [{'gameId': g_id, 'squares': game_squares}]
	response_data['matches'] = {g_id: game_matches}
	response_data['players'] = {g_id: game_players}
	response_data['nots'] = {g_id: []}
	response_data['topPlayers'] = top_players
	response_data['profs'] = game_player_profs
	response_data['invs'] = invs

	conn.close()

	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response
















@app.route("/decline_invite", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def decline_invite():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	inv_id = request_data['invId']
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""DELETE FROM invs WHERE inv_id = %s RETURNING u_id;""", (inv_id,))
	conn.commit()
	u_id = curs.fetchone()

	invs = get_invs(u_id, curs, conn)[0]

	conn.close()

	response_data = {}
	response_data['invs'] = invs

	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response
























#order alphabetically?
@app.route("/search_players", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def search_players():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	patterns = request_data['searchPattern'].strip().split()
	first_pattern = patterns[0].title()
	last_pattern =  patterns[1].title() if len(patterns) > 1 else ''
	
	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""SELECT u_id, first, last, img FROM users WHERE (first LIKE %s AND last LIKE %s) OR (first LIKE %s AND last LIKE %s) LIMIT 20;""", (first_pattern + '%', last_pattern + '%', last_pattern + '%', first_pattern + '%'))
	conn.commit()
	rows = curs.fetchall()

	otherProfiles = [{'userId': u_id, 'firstName': first, 'lastName': last, 'img': img} for u_id, first, last, img in rows]

	conn.close()

	response = jsonify(otherProfiles)
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
	from_id = request_data['fromId']
	to_id = request_data['toId']
	g_id = request_data['gameId']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""INSERT INTO invs (to_id, g_id, from_id) VALUES (%s, %s, %s);""", (to_id, g_id, from_id))
	conn.commit()

	response = Response()
	response.headers['Access-Control-Allow-Origin'] = "*"
	return response




















@app.route("/read_nots", methods=["POST", "OPTIONS"])  #what prevetns someone from posting an int to this from anywhere?
def read_nots():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	g_id = request_data['gameId']
	u_id = request_data['userId']

	conn = db_connect()
	curs = conn.cursor()

	curs.execute("""UPDATE nots SET read = TRUE WHERE g_id = %s AND to_id = %s;""", (g_id, u_id))
	conn.commit()

	conn.close()

	response = Response()
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response






















@app.route("/validate_breed", methods=["POST", "OPTIONS"]) #need to update backend database and push to everyone else... 
def validate_breed():
	if request.method == "OPTIONS":
		response = Response()
		response.headers['Access-Control-Allow-Origin'] = "*"
		response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
		return response

	request_data = request.get_json()
	img = request_data['img']
	breed = request_data['breed']
	formatted_breed = breed.lower().replace(' ', '_')
	index = request_data['index']
	g_id = request_data['gameId']
	u_id = request_data['userId']

	#get rid of 'data:image/png;base64,' and decode
	print("@@@@ " + img[:100])
	print("@@@@ " + img[22:])	
	raw_img_bytes = base64.b64decode(img[22:])

	probs = infer(consts.CURRENT_MODEL_NAME, raw_img_bytes)
	top3 = probs.take([i for i in range(3)]).values.tolist()[:3]
	for i in range(3):####
		print(top3[i][0], top3[i][1]) ###

	response_data = {}
	for i in range(3):
		if top3[i][0] == formatted_breed and top3[i][1] > PASSING_PROB:
			response_data['success'] = True

	response_data['success'] = True	 #####tempppppp for testing!!!

	if response_data.get('success'):
		conn = db_connect()
		curs = conn.cursor()

		curs.execute("INSERT INTO matches (g_id, u_id, index) VALUES (%s, %s, %s);""", (g_id, u_id, index))
		conn.commit()
		
		curs.execute("""INSERT INTO nots (g_id, from_id, to_id, type) SELECT %s, %s, u_id, %s FROM gameplayers WHERE g_id = %s AND in_game = TRUE AND u_id != %s;""", (g_id, u_id, breed, g_id, u_id))
		conn.commit()

		conn.close()

	else:
		response_data['errorMsg'] = 'SAY WRONG BREED OR INCONCLUSIVE'

	response = jsonify(response_data)
	response.headers['Access-Control-Allow-Origin'] = '*'
	return response



























def get_my_prof(u_id, curs, conn):
	curs.execute("""SELECT first, last, email, img FROM users WHERE u_id = %s;""", (u_id,))
	conn.commit()
	first, last, email, img = curs.fetchone()

	my_prof = {u_id: {'firstName': first, 'lastName': last, 'email': email, 'img': img, 'userId': u_id}}
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
			profs[from_id] = {'firstName': first, 'lastName': last, 'img': img, 'userId': from_id}

	return invs, profs


def get_g_ids(u_id, curs, conn):
	curs.execute("""SELECT g_id FROM gameplayers WHERE u_id = %s AND in_game = TRUE ORDER BY join_time""", (u_id,))
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
	curs.execute("""SELECT not_id, from_id, type, read, first, last, img FROM nots INNER JOIN users ON from_id = u_id WHERE to_id = %s AND g_id = %s ORDER BY sent_time DESC;""", (u_id, g_id))
	conn.commit()
	rows = curs.fetchall()

	nots = []
	profs = {}
	for not_id, from_id, type, read, first, last, img in rows:
		nots.append({'notId': not_id, 'fromId': from_id, 'type': type, 'read': read})
		if from_id not in profs:
			profs[from_id] = {'firstName': first, 'lastName': last, 'img': img, 'userId': from_id}

	return nots, profs


def get_players(g_id, u_id, curs, conn):
	curs.execute("""SELECT users.u_id, first, last, img FROM gameplayers INNER JOIN users ON gameplayers.u_id = users.u_id WHERE g_id = %s AND in_game = TRUE ORDER BY gameplayers.join_time;""", (g_id,))
	conn.commit()
	rows = curs.fetchall()

	players = []
	profs = {}
	for player_id, first, last, img in rows:
		players.append(player_id)
		if player_id not in profs:
			profs[player_id] = {'firstName': first, 'lastName': last, 'img': img, 'userId': player_id}

	players.insert(0, players.pop(players.index(u_id)))

	return players, profs


def get_matches(g_id, player_ids, curs, conn):
	curs.execute("""SELECT u_id, index FROM matches WHERE g_id = %s;""", (g_id,))
	conn.commit()
	rows = curs.fetchall()

	matches = {player_id: [] for player_id in player_ids}
	for u_id, index in rows:
		matches[u_id].append(index)

	return matches



def get_top_players(u_id, curs, conn):
	curs.execute("""SELECT users.u_id, first, last, img FROM gameplayers as gp1 INNER JOIN gameplayers as gp2 ON gp1.g_id = gp2.g_id INNER JOIN users ON gp2.u_id = users.u_id WHERE gp1.u_id = %s AND gp2.u_id != %s GROUP BY users.u_id, users.first, users.last, users.img ORDER BY COUNT(users.u_id);""", (u_id, u_id))
	conn.commit()
	rows = curs.fetchall()

	top_players = []
	profs = {}

	for u_id, first, last, img in rows:
		top_players.append(u_id)
		profs[u_id] = {'firstName': first, 'lastName': last, 'img': img, 'userId': u_id}

	return top_players, profs














if __name__ == "__main__":
	port = int(environ.get("PORT", 5000))
	app.run(host="0.0.0.0", port=port, debug=True)
