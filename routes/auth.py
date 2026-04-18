import json
import requests
from functools import wraps
from flask import Blueprint, redirect, url_for, session, request, flash, current_app, jsonify
from oauthlib.oauth2 import WebApplicationClient

from models import db, User
from config import Config

auth_bp = Blueprint('auth', __name__)


def get_google_provider_cfg():
    return requests.get(Config.GOOGLE_DISCOVERY_URL, timeout=5).json()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': '로그인이 필요합니다.'}), 401
            return redirect(url_for('auth.login'))
        if not User.query.get(session['user_id']):
            session.clear()
            if request.path.startswith('/api/'):
                return jsonify({'error': '로그인이 필요합니다.'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def current_user():
    if 'user_id' not in session:
        return None
    return User.query.get(session['user_id'])


@auth_bp.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    client = WebApplicationClient(Config.GOOGLE_CLIENT_ID)
    google_cfg = get_google_provider_cfg()
    authorization_endpoint = google_cfg['authorization_endpoint']
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=url_for('auth.callback', _external=True),
        scope=['openid', 'email', 'profile'],
    )
    return redirect(request_uri)


@auth_bp.route('/login/callback')
def callback():
    code = request.args.get('code')
    if not code:
        flash('인증 코드가 없습니다.', 'danger')
        return redirect(url_for('auth.login_page'))

    client = WebApplicationClient(Config.GOOGLE_CLIENT_ID)
    google_cfg = get_google_provider_cfg()
    token_endpoint = google_cfg['token_endpoint']

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=url_for('auth.callback', _external=True),
        code=code,
    )
    token_response = requests.post(
        token_url, headers=headers, data=body,
        auth=(Config.GOOGLE_CLIENT_ID, Config.GOOGLE_CLIENT_SECRET),
        timeout=10,
    )
    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_cfg['userinfo_endpoint']
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo = requests.get(uri, headers=headers, timeout=10).json()

    google_id = userinfo['sub']
    email = userinfo['email']
    name = userinfo.get('name', '')
    picture = userinfo.get('picture', '')

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User(google_id=google_id, email=email, name=name, picture=picture)
        db.session.add(user)
        db.session.commit()
    else:
        user.name = name
        user.picture = picture
        db.session.commit()

    session.permanent = True
    session['user_id'] = user.id
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login_page'))


@auth_bp.route('/')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))
