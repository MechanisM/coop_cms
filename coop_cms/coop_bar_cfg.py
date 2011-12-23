# -*- coding: utf-8 -*-
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django.template.loader import get_template
from django.template import Context

def django_admin(request, context):
    if request.user.is_staff:
        return u'<a href="{0}">{1}</a>'.format(reverse("admin:index"), _('Admin'))

def can_do(perm):
    def inner_decorator(func):
        def wrapper(request, context):
            try:
                editable = context['editable']
                article = context['article']
                if editable and request.user.has_perm(perm, article):
                    return func(request, context)
            except KeyError:
                pass
            return None
        return wrapper
    return inner_decorator

can_edit = can_do('can_edit_article')
can_publish = can_do('can_publish_article')

@can_edit
def cms_media_library(request, context):
    if context['edit_mode']:
        return u'<a href="{0}" id="coopbar_medialibrary" class="slide">{1}</a>'.format(reverse('coop_cms_media_images'), _('Media library'))

@can_edit    
def cms_upload_image(request, context):
    if context['edit_mode']:
        return u'<a href="{0}" id="coopbar_addfile" class="colorbox-form">{1}</a>'.format(reverse('coop_cms_upload_image'), _('Add image'))

@can_edit    
def cms_change_template(request, context):
    if context['edit_mode']:
        article = context['article']
        url = reverse('coop_cms_change_template', args=[article.id])
        return u'<a href="{0}" id="coopbar_changetemplate" class="colorbox-form">{1}</a>'.format(url, _('Template'))

@can_edit
def cms_save(request, context):
    if context['edit_mode']:
        return u'<a id="coopbar_save" href="{0}">{1}</a>'.format('', _('Save'))

@can_edit
def cms_cancel(request, context):
    if context['edit_mode']:
        article = context['article']
        return u'<a href="{0}">{1}</a>'.format(article.get_absolute_url(), _('Cancel'))

@can_edit
def cms_edit(request, context):
    if not context['edit_mode']:
        article = context['article']
        return u'<a href="{0}">{1}</a>'.format(article.get_edit_url(), _('Edit'))

@can_publish
def cms_publish(request, context):
    if context['edit_mode'] and context['draft']:
        return u'<a id="coopbar_publish" href="{0}">{1}</a>'.format('', _('Publish'))

@can_edit
def cms_extra_js(request, context):
    t = get_template("coop_cms/_coop_bar_js.html")
    return t.render(Context({}))

def log_out(request, context):
    if request.user.is_authenticated():
        return u'<a href="{0}">{1}</a>'.format(reverse("django.contrib.auth.views.logout"), _('Logout'))


def load_commands(coop_bar):
    coop_bar.register_command(django_admin)
    coop_bar.register_command(cms_save)
    coop_bar.register_command(cms_cancel)
    coop_bar.register_command(cms_publish)
    coop_bar.register_command(cms_edit)
    coop_bar.register_command(cms_media_library)
    coop_bar.register_command(cms_upload_image)
    coop_bar.register_command(cms_change_template)
    coop_bar.register_command(cms_extra_js)
    coop_bar.register_command(log_out)
    