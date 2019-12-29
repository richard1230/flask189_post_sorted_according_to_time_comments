from flask import (
    Blueprint,
    views,
    render_template,
    make_response,
    Response,
    Flask,
    request,
session,
url_for,
g,abort

)
from utils.captcha import Captcha
from io import BytesIO
from PIL import Image, ImageFont, ImageDraw
from utils.CCPSDK import CCPRestSDK
from utils import restful,zlcache,safeutils
import config
from .forms import SMSCaptchaForm,SignupForm,SigninForm,AddPostForm,AddCommentForm
from .models import FrontUser
from  ..models import BannerModel,BoardModel,PostModel,CommentModel,HighlightPostModel
from .decorators import login_required
from flask_paginate import  Pagination,get_page_parameter

from exts import db
import config
from sqlalchemy.sql import func

bp = Blueprint("front", __name__)  # url_prefix='cms'表示一个前缀,这里不需要


@bp.route('/')
def index():
    board_id = request.args.get('bd',type=int,default=None)
    page = request.args.get(get_page_parameter(),type=int,default=1)
    sort = request.args.get("st",type=int,default=1)
    banners = BannerModel.query.order_by(BannerModel.priority.desc()).limit(4)
    boards = BoardModel.query.all()
    # posts= PostModel.query.all()
    #开始位置和结束位置
    start =(page-1)*config.PER_PAGE
    end = start +config.PER_PAGE
    pasts = None
    total = 0

    query_obj=None
    if sort == 1:
        query_obj = PostModel.query.order_by(PostModel.create_time.desc())
    elif sort == 2:
        # 按照加精的时间倒叙排序
        query_obj = db.session.query(PostModel).outerjoin(HighlightPostModel).order_by(
            HighlightPostModel.create_time.desc(), PostModel.create_time.desc())
    elif sort == 3:
        # 按照点赞的数量排序
        query_obj = PostModel.query.order_by(PostModel.create_time.desc())
    elif sort == 4:
        # 按照评论的数量排序
        query_obj = db.session.query(PostModel).outerjoin(CommentModel).group_by(PostModel.id).order_by(
            func.count(CommentModel.id).desc(), PostModel.create_time.desc())

    if board_id:
        query_obj =query_obj.filter(PostModel.board_id==board_id)
        posts = query_obj.slice(start,end)
        total = query_obj.count()
    else:
        posts=query_obj.slice(start,end)
        total = query_obj.count()

    #bs_version表示bootstrap的版本号
    pagination = Pagination(bs_version=3, page=page,total=total,outer_window=0,inner_window=2)
    context = {
        'banners': banners,
        'boards': boards,
        'posts':posts,
        'pagination':pagination,
        'current_board':board_id,
        'current_sort':sort
    }

    return render_template('front/front_index.html',**context)


@bp.route('/p/<post_id>/')
def post_detail(post_id):
    post = PostModel.query.get(post_id)
    if not post:
        abort(404)
    return render_template('front/front_pdetail.html',post=post)


#添加帖子评论
@bp.route('/acomment/',methods=['POST'])
@login_required
def add_comment():
    form = AddCommentForm(request.form)
    if form.validate():
        content = form.content.data
        post_id = form.post_id.data
        post = PostModel.query.get(post_id)
        if post:
            comment = CommentModel(content=content)
            comment.post = post
            comment.author = g.front_user
            db.session.add(comment)
            db.session.commit()
            return restful.success()
        else:
            return restful.params_error('没有这篇帖子！')
    else:
        return restful.params_error(form.get_error())




#添加帖子
@bp.route('/apost/',methods=['GET','POST'])
@login_required
def apost():
    if request.method == 'GET':
        boards = BoardModel.query.all()
        return render_template('front/front_apost.html',boards=boards)
    else:#这里是post方法,需要表单
        form = AddPostForm(request.form)
        if form.validate():
            title = form.title.data
            content = form.content.data
            board_id = form.board_id.data
            board = BoardModel.query.get(board_id)
            if not board:
                return restful.params_error(message='没有这个板块！')
            post = PostModel(title=title,content=content)
            post.board = board
            post.author = g.front_user
            db.session.add(post)
            db.session.commit()
            return restful.success()
        else:
            return restful.params_error(message=form.get_error())



@bp.route('/test/')
def front_test():
    return render_template('front/front_test.html')


@bp.route('/captcha/')
def graph_captcha():
    text, image = Captcha.gene_graph_captcha()
    #存储图形验证码到服务器
    zlcache.set(text.lower(),text.lower())

    out = BytesIO()
    image.save(out, 'png')
    out.seek(0)
    resp = make_response(out.read())
    # print(resp)
    # resp = Response(resp,mimetype="image/png")
    # resp.context_type = 'image/png'
    resp.headers['Content-Type'] = 'image/jpg'

    return resp

# @bp.route('/sms_captcha/')
# def sms_captcha():
#     telephone=request.args.get('telephone')
#     if not telephone:
#         return restful.params_error(message='请传入手机号码')
#     accountSid = "8a216da86f17653b016f3b4046b218ab"
#     accountToken = "ac156972012a43dab1782f1f89995ac9"
#     appId = "8a216da86f17653b016f3b40471818b2"
#     rest = CCPRestSDK.REST(accountSid, accountToken, appId)
#     #下面要有产生随机的验证码函数
#     captcha= Captcha.gene_text(number=4)
#     result = rest.sendTemplateSMS(telephone, [captcha], "1")
#     if result:
#         return restful.success()
#     else:
#         return restful.params_error(message='短信验证码发送失败')

@bp.route('/sms_captcha/',methods=['POST'])
def sms_captcha():
    form = SMSCaptchaForm(request.form)
    if form.validate():
        telephone=form.telephone.data

        accountSid = "8a216da86f17653b016f3b4046b218ab"
        accountToken = "ac156972012a43dab1782f1f89995ac9"
        appId = "8a216da86f17653b016f3b40471818b2"
        rest = CCPRestSDK.REST(accountSid, accountToken, appId)
        captcha = Captcha.gene_text(number=4)
        result = rest.sendTemplateSMS(telephone, [captcha], "1")
        if result:
            #如果发送成功,存储到缓存里面(服务器里面)
            zlcache.set(telephone,captcha)


            return restful.success()
        else:
            return restful.params_error(message='短信验证码发送失败 ')
    else:
        return restful.params_error(message='参数错误')




    # telephone=request.args.get('telephone')
    # if not telephone:
    #     return restful.params_error(message='请传入手机号码')
    # accountSid = "8a216da86f17653b016f3b4046b218ab"
    # accountToken = "ac156972012a43dab1782f1f89995ac9"
    # appId = "8a216da86f17653b016f3b40471818b2"
    # rest = CCPRestSDK.REST(accountSid, accountToken, appId)
    # #下面要有产生随机的验证码函数
    # captcha= Captcha.gene_text(number=4)
    # result = rest.sendTemplateSMS(telephone, [captcha], "1")
    # if result:
    #     return restful.success()
    # else:
    #     return restful.params_error(message='短信验证码发送失败')


#这里是后台代码
class SignupView(views.MethodView):
    def get(self):
        return_to = request.referrer
        if return_to and return_to != request.url and safeutils.is_safe_url(return_to):
            return render_template('front/front_signup.html', return_to=return_to)
        else:
            return render_template('front/front_signup.html')

    #结合front/forms.py
    def post(self):
        form = SignupForm(request.form)
        if form.validate():
            telephone = form.telephone.data
            username = form.username.data
            password = form.password1.data
            user = FrontUser(telephone=telephone, username=username, password=password)
            db.session.add(user)
            db.session.commit()
            return restful.success()
        else:
            print(form.get_error())
            return restful.params_error(message=form.get_error())

##155课时(没有按照flask的来)，这里是测试代码
class SMSCodeView(views.MethodView):
    def get(self):
        #/smscode?tel=xxxxx
        telephone = request.args.get("tel")
        # telephone = request.values.get("tel")
        accountSid="8a216da86f17653b016f3b4046b218ab"
        accountToken = "ac156972012a43dab1782f1f89995ac9"
        appId ="8a216da86f17653b016f3b40471818b2"
        rest = CCPRestSDK.REST(accountSid,accountToken,appId)
        captcha = Captcha.gene_text(number=4)
        result = rest.sendTemplateSMS(telephone, [captcha], "1")
        # result= rest.sendTemplateSMS(telephone,["1234"],"1")
        print(result)
        return Response("success")



class SigninView(views.MethodView):
    def get(self):
        return_to = request.referrer
        if return_to and return_to != request.url and return_to != url_for("front.signup") and safeutils.is_safe_url(
                return_to):
            return render_template('front/front_signin.html', return_to=return_to)
        else:
            return render_template('front/front_signin.html')

    #post方法这里一般需要表单验证,这里代码在front/forms.py里面
    #这是登陆的后台代码
    def post(self):
        form = SigninForm(request.form)
        if form.validate():
            telephone = form.telephone.data
            password = form.password.data
            remember = form.remeber.data
            user = FrontUser.query.filter_by(telephone=telephone).first()
            if user and user.check_password(password):
                session[config.FRONT_USER_ID]=user.id
                if remember:
                    session.permanent = True
                return restful.success()
            else:
                return  restful.params_error(message='手机号或者密码错误')
        else:
            return restful.params_error(message=form.get_error())




bp.add_url_rule('/signup/', view_func=SignupView.as_view('signup'))
bp.add_url_rule('/signin/', view_func=SigninView.as_view('signin'))

bp.add_url_rule('/smscode/',view_func=SMSCodeView.as_view('smscode'))
