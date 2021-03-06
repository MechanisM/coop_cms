# -*- coding: utf-8 -*-
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.template.loader import get_template
from django.template import Context
from django_extensions.db.models import TimeStampedModel, AutoSlugField
from django.conf import settings
from sorl.thumbnail import default as sorl_thumbnail
import os, os.path, shutil
from django.core.urlresolvers import reverse
from django.db.models.aggregates import Max
from django.utils.html import escape
from django.core.exceptions import ValidationError
from html_field.db.models import HTMLField
from html_field import html_cleaner
from coop_cms.settings import get_article_class, get_article_logo_size
from django.contrib.staticfiles import finders
from django.core.files import File

def get_object_label(content_type, object):
    """
    returns the label used in navigation according to the configured rule
    """
    try:
        nt = NavType.objects.get(content_type=content_type)
        if nt.label_rule == NavType.LABEL_USE_SEARCH_FIELD:
            label = getattr(object, nt.search_field)
        elif nt.label_rule == NavType.LABEL_USE_GET_LABEL:
            label = object.get_label()
        else:
            label = unicode(object)
    except NavType.DoesNotExist:
        label = unicode(object)
    return escape(label)
    
def set_node_ordering(node, parent_id):
    if parent_id:
        node.parent = NavNode.objects.get(id=parent_id)
        sibling_nodes = NavNode.objects.filter(parent=node.parent)
    else:
        node.parent = None
        sibling_nodes = NavNode.objects.filter(parent__isnull=True)
    max_ordering = sibling_nodes.aggregate(max_ordering=Max('ordering'))['max_ordering'] or 0
    node.ordering = max_ordering + 1
    
def create_navigation_node(content_type, object, parent_id):
    node = NavNode(label=get_object_label(content_type, object))
    #add it as last child of the selected node
    set_node_ordering(node, parent_id)
    #associate with a content object
    node.content_type = content_type
    node.object_id = object.id
    node.save()
    return node

class NavType(models.Model):
    """Define which ContentTypes can be inserted in the tree as content"""
    
    LABEL_USE_UNICODE = 0
    LABEL_USE_SEARCH_FIELD = 1
    LABEL_USE_GET_LABEL = 2
    
    LABEL_RULE_CHOICES = (
        (LABEL_USE_UNICODE, _(u'Use object unicode')),
        (LABEL_USE_SEARCH_FIELD, _(u'Use search field')),
        (LABEL_USE_GET_LABEL, _(u'Use get_label')),
    )
    
    content_type = models.ForeignKey(ContentType, unique=True, verbose_name=_(u'django model'))
    search_field = models.CharField(max_length=200, blank=True, default="", verbose_name=_(u'search field'))
    label_rule = models.IntegerField(verbose_name=_(u'How to generate the label'),
        choices=LABEL_RULE_CHOICES, default=LABEL_USE_UNICODE)
    
    def __unicode__(self):
        return self.content_type.app_label+'.'+self.content_type.model

    class Meta:
        verbose_name = _(u'navigable type')
        verbose_name_plural = _(u'navigable types')

    
class NavNode(models.Model):
    """
    A navigation node
    Part of the tree as child of his parent
    Point on a content_object 
    """
    label = models.CharField(max_length=200, verbose_name=_("label"))
    
    parent = models.ForeignKey("NavNode", blank=True, null=True, default=0, verbose_name=_("parent"))
    ordering = models.PositiveIntegerField(_("ordering"), default=0)
    
    #generic relation
    content_type = models.ForeignKey(ContentType, verbose_name=_("content_type"))
    object_id = models.PositiveIntegerField(verbose_name=_("object id"))
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    in_navigation = models.BooleanField(_("in navigation"), default=True)
    
    def get_absolute_url(self):
        if self.content_object:
            return self.content_object.get_absolute_url()
        return ""
    
    def get_content_name(self):
        return self.content_type.model_class()._meta.verbose_name
    
    def __unicode__(self):
        return self.label
    
    class Meta:
        verbose_name = _(u'navigation node')
        verbose_name_plural = _(u'navigation nodes')
        unique_together = ('content_type', 'object_id')

    def get_children(self, in_navigation=None):
        nodes = NavNode.objects.filter(parent=self).order_by("ordering")
        if in_navigation != None:
            nodes = nodes.filter(in_navigation=in_navigation)
        return nodes
    
    def has_children(self):
        return self.get_children(True).count()
        
    def get_siblings(self, in_navigation=None):
        nodes = NavNode.objects.filter(parent=self.parent).order_by("ordering")
        if in_navigation != None:
            nodes = nodes.filter(in_navigation=in_navigation)
        return nodes
    
    def get_progeny(self, level=0):
        progeny = []
        progeny.append((self, level))
        for child in NavNode.objects.filter(parent=self).order_by("ordering"):
            progeny.extend(child.get_progeny(level+1))
        return progeny
    
    def as_jstree(self):
        li_content = u'<a href="{0}">{1}</a>'.format(self.get_absolute_url(), self.label)
        
        children_li = [child.as_jstree() for child in self.get_children()]
        
        return u'<li id="node_{0}" rel={3}>{1}<ul>{2}</ul></li>'.format(
            self.id, li_content, u''.join(children_li), "in_nav" if self.in_navigation else "out_nav"
        )
    
    def _get_li_content(self, li_template):
        if li_template:
            t = li_template if hasattr(li_template, 'render') else get_template(li_template)
            return t.render(Context({'node': self}))
        else:
            return u'<a href="{0}">{1}</a>'.format(self.get_absolute_url(), self.label)
            
    def _get_ul_format(self, ul_template):
        if ul_template:
            t = ul_template if hasattr(ul_template, 'render') else get_template(ul_template)
            return t.render(Context({'node': self}))
        else:
            return u'<ul>{0}</ul>'
        
    def _get_li_args(self, li_args):
        if li_args:
            t = li_args if hasattr(li_args, 'render') else get_template(li_args)
            return t.render(Context({'node': self}))
        else:
            return u''
    
    def as_navigation(self, li_template=None, css_class="", ul_template=None, li_args=None):
        #Display the node and his children as nested ul and li html tags.
        #li_template is a custom template that can be passed
        
        if not self.in_navigation:
            return ""
        
        children_li = [child.as_navigation(li_template) for child in self.get_children(in_navigation=True)]
        ul_format = self._get_ul_format(ul_template)
        children_html = ul_format.format(u''.join(children_li)) if children_li else ""
        args = self._get_li_args(li_args)
        if args:
            css_class = " "+args
        return u'<li{0}>{1}{2}</li>'.format(css_class, self._get_li_content(li_template), children_html)
        
    def as_breadcrumb(self, li_template=None, css_class=""):
        html = self.parent.as_breadcrumb(li_template) if self.parent else u""
        return html + u'<li{0}>{1}</li>'.format(css_class, self._get_li_content(li_template))

    def children_as_navigation(self, li_template=None, css_class=""):
        children_li = [u'<li{0}>{1}</li>'.format(css_class, child._get_li_content(li_template))
            for child in self.get_children(in_navigation=True)]
        return  u''.join(children_li)
        
    def siblings_as_navigation(self, li_template=None, css_class=""):
        siblings_li = [u'<li{0}>{1}</li>'.format(css_class, sibling._get_li_content(li_template))
            for sibling in self.get_siblings(in_navigation=True)]
        return  u''.join(siblings_li)

    def check_new_navigation_parent(self, parent_id):
        if parent_id == self.id:
            raise ValidationError(_(u'A node can not be its own parent'))
        
        if parent_id:
            cur_node = NavNode.objects.get(id=parent_id)
            while cur_node:
                if cur_node.id == self.id:
                    raise ValidationError(_(u'A node can not be child of its own child'))
                cur_node = cur_node.parent

    
class NavTree(models.Model):
    last_update = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = verbose_name = _(u'Navigation tree')

content_cleaner = html_cleaner.HTMLCleaner(
    allow_tags=['a', 'img', 'p', 'br', 'b', 'i', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'sup', 'pre', 'ul', 'li', 'ol', 'table', 'th', 'tr', 'td', 'tbody', 'span', 'div',
        'strong','u','dd','dt','dl','hr','em','font','iframe','object','param','embed'],
        #iframe is a security risk but needed until we find how to integrate oembed
    allow_attrs_for_tag={'a': ['href', 'target'], 'img': ['src', 'alt']}
)
title_cleaner = html_cleaner.HTMLCleaner(allow_tags=['br','span','em','i','strong','b','font','u'])

    
class ArticleSection(models.Model):
    name = models.CharField(_(u'name'), max_length=100)
    
    def __unicode__(self):
        return self.name
    
class BaseArticle(TimeStampedModel):
    """An article : static page, blog item, ..."""
    
    DRAFT = 0
    PUBLISHED = 1
    
    PUBLICATION_STATUS = (
        (DRAFT, _(u'Draft')),
        (PUBLISHED, _(u'Published')),
    )

    def get_logo_folder(self, filename):
        try:
            img_root = settings.CMS_ARTICLE_LOGO_FOLDER
        except AttributeError:
            img_root = 'cms_logos'
        return u'{0}/{1}/{2}'.format(img_root, self.id, filename)
    
    slug = AutoSlugField(populate_from='title', max_length=100, unique=True)
    title = HTMLField(title_cleaner, verbose_name=_(u'title'), default=_('Page title'))
    #content = HTMLField(content_cleaner, verbose_name=_(u'content'), default=_('Page content'))
    content = models.TextField(_(u'content'), default=_('Page content'))
    publication = models.IntegerField(_(u'publication'), choices=PUBLICATION_STATUS, default=DRAFT)
    template = models.CharField(_(u'template'), max_length=200, default='', blank=True)
    logo = models.ImageField(upload_to=get_logo_folder, blank=True, null=True, default='')
    temp_logo = models.ImageField(upload_to=get_logo_folder, blank=True, null=True, default='')
    summary = models.TextField(_(u'Summary'), blank=True, default='')
    section = models.ForeignKey(ArticleSection, verbose_name=_(u'Section'), blank=True, null=True, default=None, related_name="%(app_label)s_%(class)s_rel")

    def logo_thumbnail(self, temp=False, logo_size=None):
        logo = self.temp_logo if (temp and self.temp_logo) else self.logo
        size = logo_size or get_article_logo_size(self)
        if logo:
            file = logo.file
        else:
            file = self._get_default_logo()
        return sorl_thumbnail.backend.get_thumbnail(file, size, crop='center')
    
    def _get_default_logo(self):
        #copy from static to media in order to use sorl thumbnail without raising a suspicious operation
        filename = 'img/default-logo.png'
        media_filename = os.path.normpath(settings.MEDIA_ROOT+'/coop_cms/'+filename)
        if not os.path.exists(media_filename):
            dir = os.path.dirname(media_filename)
            if not os.path.exists(dir):
                os.makedirs(dir)
            static_filename = finders.find(filename)
            shutil.copyfile(static_filename, media_filename)
        return File(open(media_filename, 'r'))
    
    class Meta:
        verbose_name = _(u"article")
        verbose_name_plural = _(u"articles")
        abstract = True
    
    def __unicode__(self):
        return self.title
    
    def _get_navigation_parent(self):
        ct = ContentType.objects.get_for_model(get_article_class())
        nodes = NavNode.objects.filter(object_id=self.id, content_type=ct)
        if nodes.count():
            return nodes[0].parent.id if nodes[0].parent else 0
        else:
            return None
    
    def _set_navigation_parent(self, value):
        ct = ContentType.objects.get_for_model(get_article_class())
        already_in_navigation = self.id and NavNode.objects.filter(content_type=ct, object_id=self.id)
        if value != None and not already_in_navigation:
            create_navigation_node(ct, self, value)
        else:
            try:
                node = NavNode.objects.get(content_type=ct, object_id=self.id)
                if value == None:
                    node.delete()
                else:
                    node.parent = NavNode.objects.get(id=value) if value else None
                    if node.parent:
                        #raise ValidationError if new parent is not valid
                        node.check_new_navigation_parent(node.parent.id)
                    set_node_ordering(node, node.parent.id if node.parent else 0)
                    node.save()
            except NavNode.DoesNotExist:
                pass
    
    navigation_parent = property(_get_navigation_parent, _set_navigation_parent,
        doc=_("set the parent in navigation."))
    
    def save(self, *args, **kwargs):
        ret = super(BaseArticle, self).save(*args, **kwargs)
        parent_id = getattr(self, '_navigation_parent', None)
        if parent_id != None:
            self.navigation_parent = parent_id
        return ret
    
    def get_label(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('coop_cms_view_article', args=[self.slug])
        
    def get_edit_url(self):
        return reverse('coop_cms_edit_article', args=[self.slug])
        
    def get_cancel_url(self):
        return reverse('coop_cms_cancel_edit_article', args=[self.slug])
    
    def get_publish_url(self):
        return reverse('coop_cms_publish_article', args=[self.slug])
        
    def _can_change(self, user):
        ct = ContentType.objects.get_for_model(get_article_class())
        perm = '{0}.change_{1}'.format(ct.app_label, ct.model)
        return user.has_perm(perm)
        
    def can_view_article(self, user):
        if self.publication != BaseArticle.PUBLISHED:
            return self.can_edit_article(user)
        else:
            return True
    
    def can_edit_article(self, user):
        return self._can_change(user)
    
    def can_publish_article(self, user):
        return self._can_change(user)
    
class Link(TimeStampedModel):
    """Link to a given url"""
    url = models.URLField()
    
    def get_absolute_url(self):
        return self.url
    
    def get_label(self):
        if self.url.find('http://')==0:
            return self.url[7:]
        return self.url
    
    def __unicode__(self):
        return self.url

    class Meta:
        verbose_name = _(u"link")
        verbose_name_plural = _(u"links")

def get_img_folder(instance, filename):
    try:
        img_root = settings.IMAGE_FOLDER
    except AttributeError:
        img_root = 'img'
        
    return u'{0}/{1}/{2}'.format(img_root,
        instance.created.strftime('%Y%d%m%H%M%S'), filename)

class Media(TimeStampedModel):
    name = models.CharField(_('name'), max_length=200, blank=True, default='')

    def __unicode__(self):
        return self.name

    class Meta:
        abstract = True

class Image(Media):
    file = models.ImageField(_('file'), upload_to=get_img_folder)
    
    def as_thumbnail(self):
        return sorl_thumbnail.backend.get_thumbnail(self.file.file, "64x64", crop='center')
        
    def get_absolute_url(self):
        return self.file.url
        
    class Meta:
        verbose_name = _(u'image')
        verbose_name_plural = _(u'images')    

class Document(Media):
    def get_doc_folder(self, filename):
        if self.is_private:
            try:
                doc_root = settings.DOCUMENT_FOLDER
            except AttributeError:
                doc_root = 'docs'
        else:
            try:
                doc_root = settings.PRIVATE_DOCUMENT_FOLDER
            except AttributeError:
                doc_root = 'private_docs'    
        
        filename = os.path.basename(filename)
        
        return u'{0}/{1}/{2}'.format(doc_root,
            self.created.strftime('%Y%d%m%H%M%S'), filename)
    
    file = models.FileField(_('file'), upload_to=get_doc_folder)
    is_private = models.BooleanField(default=False)

    def can_download_doc(self, user):
        return user.is_authenticated()
        
    def get_download_url(self):
        if self.is_private:
            return reverse('coop_cms_download_doc', args=[self.id])
        else:
            return self.file.url
    
    def get_ico_url(self):
        root, ext = os.path.splitext(self.file.name)
        ext = ext[1:] #remove leading dot
        if ext in ('pdf', 'doc', 'xls', 'txt'):
            return settings.STATIC_URL+u'img/{0}.png'.format(ext)
        else:
            return settings.STATIC_URL+u'img/default-icon.png'
            
    class Meta:
        verbose_name = _(u'document')
        verbose_name_plural = _(u'documents')

class PieceOfHtml(models.Model):
    div_id = models.CharField(verbose_name=_(u"identifier"), max_length=100, db_index=True)    
    content = HTMLField(content_cleaner, verbose_name=_(u"content"), default="", blank=True)

    def __unicode__(self):
        return self.div_id
    
    class Meta:
        verbose_name = _(u'piece of HTML')
        verbose_name_plural = _(u'pieces of HTML')

#delete node when content object is deleted
from django.db.models.signals import pre_delete

def remove_from_navigation(sender, instance, **kwargs):
    if hasattr(instance, 'id'):
        try:
            ct = ContentType.objects.get_for_model(instance)
            node = NavNode.objects.get(content_type=ct, object_id=instance.id)
            node.delete()
        except (NavNode.DoesNotExist, ContentType.DoesNotExist):
            pass
pre_delete.connect(remove_from_navigation)

class NewsletterItem(models.Model):
    content_type = models.ForeignKey(ContentType, verbose_name=_("content_type"))
    object_id = models.PositiveIntegerField(verbose_name=_("object id"))
    content_object = generic.GenericForeignKey('content_type', 'object_id')
    
    class Meta:
        unique_together = (("content_type", "object_id"),)
        verbose_name = _(u'newsletter item')
        verbose_name_plural = _(u'newsletter items')
    
    def __unicode__(self):
        return u'{0}: {1}'.format(self.content_type, self.content_object)

class Newsletter(models.Model):
    subject = models.CharField(max_length=200, verbose_name=_(u'subject'), blank=True, default="")
    content = HTMLField(content_cleaner, verbose_name=_(u"content"), default="<br>", blank=True)
    items = models.ManyToManyField(NewsletterItem, blank=True)
    template = models.CharField(_(u'template'), max_length=200, default='', blank=True)

    def get_items(self):
        return [item.content_object for item in self.items.all()]
        
    def can_edit_newsletter(self, user):
        return user.has_perm('coop_cms.change_newsletter')
    
    def get_absolute_url(self):
        return reverse('coop_cms_view_newsletter', args=[self.id])
        
    def get_edit_url(self):
        return reverse('coop_cms_edit_newsletter', args=[self.id])
        
    def get_template_name(self):
        template = self.template
        if not template:
            self = 'coop_cms/newsletter.html'
        return template
        
    def __unicode__(self):
        return self.subject
        
    class Meta:
        verbose_name = _(u'newsletter')
        verbose_name_plural = _(u'newsletters')    

class NewsletterSending(models.Model):
    
    newsletter = models.ForeignKey(Newsletter) 
    
    scheduling_dt = models.DateTimeField(_(u"scheduling date"), blank=True, default=None, null=True)
    sending_dt = models.DateTimeField(_(u"sending date"), blank=True, default=None, null=True)

    def __unicode__(self):
        return self.newsletter.subject

    class Meta:
        verbose_name = _(u'newsletter sending')
        verbose_name_plural = _(u'newsletter sendings')
        
    