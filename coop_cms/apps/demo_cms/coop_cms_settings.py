# -*- coding: utf-8 -*-

COOP_CMS_ARTICLE_CLASS = 'coop_cms.apps.demo_cms.models.Article'
COOP_CMS_ARTICLE_FORM = 'coop_cms.apps.demo_cms.forms.ArticleForm'

COOPBAR_MODULES = ('coop_cms.apps.demo_cms.my_coop_bar',)
DJALOHA_LINK_MODELS = ('demo_cms.Article',)
COOP_CMS_ARTICLE_LOGO_SIZE = "128x128"

COOP_CMS_ARTICLE_TEMPLATES = 'coop_cms.apps.demo_cms.get_article_templates'
#COOP_CMS_ARTICLE_TEMPLATES = (
#    ('standard.html', 'Standard'),
#    ('homepage.html', 'Homepage'),
#    ('blog.html', 'Blog'),
#)