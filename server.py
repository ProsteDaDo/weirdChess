from flask import Flask, request, render_template
from flask_socketio import SocketIO, send, emit

import eventlet
import random
import time
import _thread

import game
from randomPlayer import RandomPlayer
from negamax import NegamaxPlayer
from negamax2 import NegamaxPlayer2
from negamax2qe import NegamaxPlayer2QE
from negamax2qeKm import NegamaxPlayer2QEKM

from mcts import MCTS
from mctsMem import MCTSMemory
from mctsEC import MCTSEarlyCutout


app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecret'

socketio = SocketIO(app, ping_timeout=50, ping_interval=30)#, async_mode="threading")


lobby = []
users = {}
usersAI = {}
games = {}

aiPool = [NegamaxPlayer2QEKM]

username_sid = {}
sid_username = {}


@app.route("/")
@app.route("/index")
def main_page():
    return render_template("index.html")

@app.route("/rules")
def rule_page():
    return render_template("rules.html")

@app.route("/game")
def game_page():
    return render_template("game.html")

@socketio.on("connect")
def connected():
    print("User connected with SID:", request.sid)

@socketio.on("joinLobby")
def join_lobby():
    user = request.sid

    lobby.append(user)
    join_two(user)

@socketio.on("leaveLobby")
def leave_lobby():
    lobby.remove(request.sid)

@socketio.on("setUsername")
def username(name):
    userId = request.sid
    suffix = "".join([random.choice([str(x) for x in range(0, 10)]) for _ in range(0, 4)])

    while name + suffix in username_sid.keys():
        suffix = "".join([random.choice([str(x) for x in range(0, 10)]) for _ in range(0, 4)])

    username_sid[name + suffix] = userId
    sid_username[userId] = name + suffix

    print(username_sid)
    print(sid_username)

    emit("setNick", name + suffix)

@socketio.on("joinFriend")
def join_friend(name):
    usr1 = request.sid

    if name not in username_sid.keys():
        socketio.emit("noFriend")
        return

    usr2 = username_sid[name]

    try:
        lobby.remove(usr1)
    except ValueError:
        pass

    try:
        lobby.remove(usr2)
    except ValueError:
        pass

    users[usr1] = usr2
    users[usr2] = usr1

    newGame = game.Game()
    games[usr1] = newGame
    games[usr2] = newGame

    board = newGame.board_to_text()
    moves = newGame.moves_to_json()
    start = random.choice((0, 1))

    usr1name = "noname" if usr1 not in sid_username.keys() else sid_username[usr1]
    usr2name = "noname" if usr2 not in sid_username.keys() else sid_username[usr2]

    print("Joining", usr1 + "(" + usr1name + ")", usr2 + "(" + usr2name + ")")

    emit("joinGame", (start, usr2name, board, moves), room = usr1)
    emit("joinGame", (1 - start, usr1name, board, moves), room = usr2)

def join_two(usr1):
    freeUsers = [x for x in lobby if x != usr1]

    if len(freeUsers) < 1:
        return

    usr2 = freeUsers[0]

    lobby.remove(usr1)
    lobby.remove(usr2)

    users[usr1] = usr2
    users[usr2] = usr1

    newGame = game.Game()
    games[usr1] = newGame
    games[usr2] = newGame

    board = newGame.board_to_text()
    moves = newGame.moves_to_json()
    start = random.choice((0, 1))

    usr1name = "noname" if usr1 not in sid_username.keys() else sid_username[usr1]
    usr2name = "noname" if usr2 not in sid_username.keys() else sid_username[usr2]

    print("Joining", usr1 + "(" + usr1name + ")", usr2 + "(" + usr2name + ")")

    emit("joinGame", (start, usr2name, board, moves), room = usr1)
    emit("joinGame", (1 - start, usr1name, board, moves), room = usr2)

@socketio.on("joinAI")
def join_ai():
    usr = request.sid
    start = random.choice((0, 1))

    ai = random.choice(aiPool)(2 - start)
    usersAI[usr] = ai

    newGame = game.Game()
    games[usr] = newGame

    board = newGame.board_to_text()
    moves = newGame.moves_to_json()

    emit("joinGame", (1 - start, "AI", board, moves), room=usr)

    if start == 1:
        socketio.sleep(0.5)
        socketio.start_background_task(aiTurn, newGame, ai, usr)

@socketio.on("disconnect")
def disconnected():
    usr1 = request.sid

    try:
        lobby.remove(usr1)
    except ValueError:
        pass

    try:
        usr2 = users[usr1]
        emit("leaveGame", room = users[usr1])
        del users[usr1]
        del users[usr2]
        del games[usr1]
        del games[usr2]
    except KeyError:
        pass

    try:
        del username_sid[sid_username[usr1]]
        del sid_username[usr1]
    except KeyError:
        pass

    print("User disconnected with SID:", usr1)
    print(users)

@socketio.on("diss")
def diss():
    print("before undload")
    disconnected()

@socketio.on("turn")
def takeTurn(turn):
    usr = request.sid

    theGame = games[usr]
    move = theGame.string_to_move(turn)
    theGame.make_move(move)

    board = theGame.board_to_text()
    moves = theGame.moves_to_json()

    if usr in users.keys():
        emit("madeTurn", (board, moves), room=users[usr])
        emit("updateBoard", board, room=usr)

        if theGame.state != -1:
            if theGame.state == theGame.currentPlayer:
                emit("endGame", 0, room=usr)
                emit("endGame", 1, room=users[usr])
            elif theGame.state == 3 - theGame.currentPlayer:
                emit("endGame", 1, room = usr)
                emit("endGame", 0, room = users[usr])

            del games[users[usr]]
            del games[usr]

            del users[users[usr]]
            del users[usr]

    elif usr in usersAI.keys():
        emit("updateBoard", board, room=usr)

        if theGame.state != -1:
            if theGame.state == theGame.currentPlayer:
                emit("endGame", 0, room=usr)
            elif theGame.state == 3 - theGame.currentPlayer:
                emit("endGame", 1, room=usr)

            del games[usr]
            del usersAI[usr]

            return

        socketio.sleep(0.5)
        socketio.start_background_task(aiTurn, games[usr], usersAI[usr], usr)

def aiTurn(theGame, ai, opponent):
    with app.test_request_context('/game'):
        theGame.make_move(ai.choose(theGame))

        board = theGame.board_to_text()
        moves = theGame.moves_to_json()

        socketio.emit("madeTurn", (board, moves), room = opponent)

        if theGame.state != -1:
            if theGame.state == theGame.currentPlayer:
                socketio.emit("endGame", 1, room = opponent)
            elif theGame.state == 3 - theGame.currentPlayer:
                socketio.emit("endGame", 0, room = opponent)

            del games[opponent]
            del usersAI[opponent]

@socketio.on("resign")
def handle_resign():
    usr1 = request.sid

    if usr1 in users.keys():
        usr2 = users[usr1]

        emit("endGame", 2, room=usr1)
        emit("endGame", 3, room=usr2)

        del games[usr1]
        del games[usr2]

        del users[usr1]
        del users[usr2]

    elif usr1 in usersAI.keys():
        emit("endGame", 2, room=usr1)

        del games[usr1]
        del usersAI[usr1]


if __name__ == '__main__':
    socketio.run(app)