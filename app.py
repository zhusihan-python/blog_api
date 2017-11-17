from flask import Flask, abort, make_response, jsonify, request, url_for, g
from flask_httpauth import HTTPBasicAuth
from flask_sqlalchemy import SQLAlchemy
from flask_script import Manager, Server
from flask_migrate import Migrate, MigrateCommand


app = Flask(__name__)
app.config['DEBUG'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:pass123@localhost:3306/blogapi"
db = SQLAlchemy(app)
migrate = Migrate(app, db)
manager = Manager(app)

manager.add_command("server", Server())
manager.add_command('db', MigrateCommand)

auth = HTTPBasicAuth()


@auth.verify_password
def verify_password(username, password):
    user = User.query.filter_by(username=username).first()
    if not user or not user.password == password:
        return False
    g.user = user
    return True


@manager.shell
def make_shell_context():
    return dict(app=app, db=db, User=User, Post=Post, Role=Role)


class ValidationError(ValueError):
    pass


roles = db.Table(
    'role_users',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'))
)


class User(db.Model):
    id = db.Column(db.Integer(), primary_key=True)
    username = db.Column(db.String(255))
    password = db.Column(db.String(255))
    posts = db.relationship(
        'Post',
        backref='user',
        lazy='dynamic'
    )

    roles = db.relationship(
        'Role',
        secondary=roles,
        backref=db.backref('users', lazy='dynamic')
    )

    def __init__(self, username):
        self.username = username

    def __repr__(self):
        return "<User '{}'>".format(self.username)


class Post(db.Model):
    id = db.Column(db.Integer(), primary_key=True)
    title = db.Column(db.String(255))
    text = db.Column(db.Text())
    publish_date = db.Column(db.DateTime())
    user_id = db.Column(db.Integer(), db.ForeignKey('user.id'))

    def __init__(self, title, text, publish_date):
        self.title = title
        self.text = text
        self.publish_date = publish_date

    def __repr__(self):
        return "<Post '{}'>".format(self.title)

    @staticmethod
    def from_json(json_post):
        title = json_post.get('title')
        text = json_post.get('text')
        publish_date = json_post.get('publish_date')
        if text is None or text == '':
            raise ValidationError('post does not have text')
        return Post(title=title, text=text, publish_date=publish_date)

    def to_json(self):
        json_post = {
            'url': url_for('get_post', post_id=self.id, _external=True),
            'text': self.text,
            'publish_date': self.publish_date,
            'user_id': self.user_id
        }
        return json_post


class Role(db.Model):
    id = db.Column(db.Integer(), primary_key=True)
    rolename = db.Column(db.String(255), unique=True)
    description = db.Column(db.String(255))

    def __init__(self, rolename):
        self.rolename = rolename

    def __repr__(self):
        return "<Role '{}'>".format(self.rolename)


def get_post_by_id(post_id):
    post = Post.query.get(post_id)
    return post


def delete_post_by_id(post_id):
    post = Post.query.get(post_id)
    db.session.delete(post)
    db.session.commit()


@app.errorhandler(404)
def not_found(e):
    return make_response(jsonify({'error': 'Not found'}), 404)


def forbidden(message):
    response = jsonify({'error': 'forbidden', 'message': message})
    response.status_code = 403
    return response


@app.route('/blog/api/v1.0/posts', methods=['GET'])
def all_post():
    posts = Post.query.order_by(
        Post.publish_date.desc()
    ).all()
    return jsonify({'posts': [post.to_json() for post in posts]})


@app.route('/blog/api/v1.0/posts/<int:post_id>', methods=['GET'])
def get_post(post_id):
    post = get_post_by_id(post_id)
    if post:
        return jsonify(post.to_json())
    else:
        abort(404)


@app.route('/blog/api/v1.0/add', methods=['POST'])
@auth.login_required
def add():
    post = Post.from_json(request.json)
    post.user_id = g.user.id
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_json()), 201


@app.route('/blog/api/v1.0/posts/<int:post_id>', methods=['PUT'])
@auth.login_required
def update_post(post_id):
    post = get_post_by_id(post_id)
    username = g.user.username
    user = User.query.filter_by(
        username=username
    ).first()
    if post.user_id != user.id and username != 'admin':
        return forbidden('Insufficient permissions')
    post.title = request.json.get('title')
    post.text = request.json.get('text')
    post.publish_date = request.json.get('publish_date')
    db.session.add(post)
    db.session.commit()
    return jsonify(post.to_json())


@app.route('/blog/api/v1.0/posts/<int:post_id>', methods=['DELETE'])
@auth.login_required
def delete(post_id):
    res = {
        "status": 1,
        "message": "success"
    }
    post = get_post_by_id(post_id)
    if not post:
        abort(404)

    username = g.user.username
    user = User.query.filter_by(
        username=username
    ).first()
    if post.user_id != user.id and username != 'admin':
        return forbidden('Insufficient permissions')

    delete_post_by_id(post_id)
    return jsonify(res)


if __name__ == '__main__':
    manager.run()