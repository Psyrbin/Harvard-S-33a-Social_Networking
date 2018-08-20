import sqlite3
import os
from flask import Flask, session, render_template, request, redirect, url_for
from flask_session import Session
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
socketio = SocketIO(app)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = sqlite3.connect('database.db')
db.row_factory = sqlite3.Row

@app.route('/')
def index():   
    if session.get('user') == None:
        return render_template('index.html', message=None)
    else:
        return redirect(url_for('user', user=session.get('user')))


#user page
@app.route('/<string:user>', methods=['GET', 'POST'])
def user(user, edit=False):
    if request.method == 'POST':
    #add comment
        name = session.get('user')
        data = request.form.get('data')
        post = request.form.get('post')

        db.execute('INSERT INTO comments (user, post, data) VALUES (:name, :post, :data)', {'name': name, 'post': post, 'data':data})
        db.commit()

    postable = False
    if session.get('user') == user:
        postable = True

    if len(db.execute('SELECT * FROM users WHERE name=:name', {'name': user}).fetchall()) == 0:
        return render_template('no_user.html', name=user)

    personal = db.execute('SELECT data FROM personal WHERE user=:user', {'user': user}).fetchall()
    db.commit()

    if len(personal) == 0:
        personal = None
    else:
        personal = personal[0]['data']

    posts = db.execute('SELECT id, data from posts WHERE user=:user', {'user': user}).fetchall()
    db.commit()

    comments = {}
    if len(posts) == 0:
        posts = None
    else:
        posts = list(reversed(posts))
        for post in posts:
            post_comments = db.execute('SELECT * FROM comments WHERE post=:post', {'post': post['id']}).fetchall()
            comments[post['id']] = post_comments

    return render_template('user.html', personal=personal, user=user, postable=postable, posts=posts, comments=comments, edit=edit, you=session.get('user'))


#login page
@app.route('/login', methods=['POST'])
def login():
    name = request.form.get('name')
    password = request.form.get('password')

    users = db.execute('SELECT * FROM users WHERE name=:name AND password=:pass', {'name': name, 'pass': str(password)}).fetchall()
    db.commit()

    if len(users) == 0:
        return render_template('index.html', message='Incorect username or password')
    name = users[0]['name']
    session['user'] = name
    return user(name)



#registration page
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html', message=None)

    name = request.form.get("name")
    password = request.form.get("password")
    password_conf = request.form.get("password_conf")

    if password != password_conf:
        return render_template('register.html', message="Passwords don't match")
    if password == '':
        return render_template('register.html', message="Password is empty")
    if name == '':
        return render_template('register.html', message="Name is empty")

    if len(db.execute('SELECT * FROM users WHERE name = :name', {'name': name}).fetchall()) > 0:
        return render_template('register.html', message='User with this name already exists. Please try another.')

    db.execute("INSERT INTO users (name, password) VALUES (:name, :password)", {"name": name, "password": password})
    db.commit()

    return render_template("index.html", message='Registration complete')


#logout
@app.route('/logout')
def logout():
    session['user'] = None
    return render_template('index.html', message='Logged out')


#edit personal information
@app.route('/edit_personal')
def edit_personal():
    return user(session.get('user'), edit=True)


#submit personal information
@app.route('/submit_personal', methods=['POST'])
def submit_personal():
    name = session.get('user')
    data = request.form.get('data')

    if len(db.execute('SELECT * FROM personal WHERE user=:name', {'name': name}).fetchall()) > 0:
        db.execute('UPDATE personal SET data=:data WHERE user=:name', {'data': data, 'name': name})
    else:
        db.execute('INSERT INTO personal (user, data) VALUES (:name, :data)', {'name': name, 'data': data})
    db.commit()

    return redirect(url_for('user', user=name))


#new post on the page
@app.route('/new_post', methods=['POST'])
def new_post():
    name = session.get('user')
    data = request.form.get('data')
    db.execute('INSERT INTO posts (user, data) VALUES (:name, :data)', {'name': name, 'data': data})
    db.commit()

    return redirect(url_for('user', user=name))


#delete your post
@app.route('/delete_post', methods=['POST'])
def delete_post():
    name = session.get('user')
    post = request.form.get('post')
    db.execute('DELETE FROM posts WHERE id=:post', {'post': post})
    db.commit()
    return redirect(url_for('user', user=name))


#messages page
@app.route('/messages')
def messages():
    name = session.get('user')
    messages = db.execute('SELECT * FROM messages WHERE sender=:name OR receiver=:name', {'name':name}).fetchall()
    db.commit()
    users = []
    last_message = {}
    for message in messages:
        if message['sender'] != name:
            last_message[message['sender']] = message
            if message['sender'] not in users:
                users.append(message['sender'])
        else:
            last_message[message['receiver']] = message
            if message['receiver'] not in users:
                users.append(message['receiver'])

    return render_template('messages.html', users=users, last_message=last_message, you=name)


#dialogue with another user
@app.route('/conversation-<string:user>')
def conversation(user):
    name = session.get('user')
    received = db.execute('SELECT * FROM messages WHERE sender=:user AND receiver=:name', {'name': name, 'user': user}).fetchall()
    #mark new messages as read
    for message in received:
        if message['read'] == 0:
            db.execute('UPDATE messages SET read=1 WHERE id=:id', {'id': message['id']})

    messages = db.execute('SELECT * FROM messages WHERE (sender=:name AND receiver=:user) OR (sender=:user AND receiver=:name)', {'name': name, 'user': user}).fetchall()
    db.commit()

    return render_template('conversation.html', user=user, messages=messages, you=name)


#search page
@app.route('/search')
def search():
    return render_template('search.html', you=session.get('user'))


#search results
@app.route('/search_results', methods=['POST'])
def search_results():
    data = request.form.get('search')
    data = '%' + data + '%'
    results = db.execute('SELECT * FROM users WHERE name LIKE :data', {'data': data}).fetchall()
    db.commit()

    return render_template('search_results.html', results=results, you=session.get('user'))


#someone sent a message
@socketio.on('new message')
def new_message(data):
    db.execute('INSERT INTO messages (sender, receiver, data, read) VALUES (:sender, :receiver, :data, 0)', {'sender': data['from'], 'receiver': data['to'], 'data': data['text']})
    db.commit()

    emit('new message', data, broadcast=True)


#someone opened dialogue with another user
@socketio.on('messages read')
def read(data):
    messages = db.execute('SELECT * FROM messages WHERE sender=:sender AND receiver = :receiver', {'sender': data['from'], 'receiver': data['to']}).fetchall()
    for message in messages:
        if message['read'] == 0:
            db.execute('UPDATE messages SET read=1 WHERE id=:id', {'id': message['id']})
    db.commit()

    emit('messages read', {'from': data['from'], 'to': data['to']}, broadcast=True)