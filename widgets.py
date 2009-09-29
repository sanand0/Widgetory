import wsgiref.handlers, sys, logging, datetime, re
from BeautifulSoup                        import BeautifulSoup
from google.appengine.ext                 import webapp, db
from google.appengine.api                 import users, urlfetch, memcache
from google.appengine.ext.webapp          import template
from google.appengine.api.urlfetch_errors import *
from soupselect                           import select
from itertools                            import islice

# toohey testing commit

# Kludge to handle Python 2.6: http://stackoverflow.com/questions/790001/cannot-run-appengine-admin-on-devserver/1372538#1372538
if sys.version[:3] == "2.6": logging.logMultiprocessing = 0
MAX_COUNT = 10
NOW = datetime.datetime.now()

def model_from_form(model, request, default={}):
    '''Makes a model out of a request. For example, if I submit a form with a subset of the parameters for a model,
    those parameters are used to create the model. A default parameter dictionary is also provided.
    If a class is passed, creates a new instance. If an instance is passed, updates it.'''

    # Take the default parameters and override with the request parameters
    params = default.copy()
    for key in request.arguments(): params[str(key)] = request.get(key)

    # If model is an instance, use it. Otherwise, assume it's the class, and create a new instance later
    output = isinstance(model, db.Model) and model or None

    # Convert to the right data type
    properties = model.properties()
    map_data_type = { basestring: unicode }
    errors = {}
    for key in properties:
        if key in params:
            data_type = properties[key].data_type
            data_type = map_data_type.get(data_type, data_type)
            try:
                params[key] = data_type(params[key])
                if output: setattr(output, key, params[key])
            except ValueError: errors[key] = (params[key], data_type)

    return errors and (None, errors) or (output or model(**params), None)

class Widget(db.Model):
    user    = db.UserProperty       (required=False)                    # Author
    created = db.DateTimeProperty   (required=True, auto_now_add=True)  # created date
    updated = db.DateTimeProperty   (required=True, auto_now=True)      # updated date

    name    = db.StringProperty     (required=True)                     # widget name
    url     = db.StringProperty     (required=True)                     # data source
    image   = db.StringProperty     ()                                  # image url
    count   = db.IntegerProperty    (default=0)                         # Max elements per widget
    refresh = db.IntegerProperty    (default=24)                        # Refresh every 'refresh' hours
    loop    = db.StringProperty     ()                                  # Loop element selector
    header  = db.TextProperty       ()                                  # Header of the widget
    body    = db.TextProperty       ()                                  # Body of the widget
    footer  = db.TextProperty       ()                                  # Footer of the widget
    width   = db.IntegerProperty    (required=True, default=100)        # Width of the IFrame
    height  = db.IntegerProperty    (required=True, default=100)        # Height of the IFrame

    usage   = db.IntegerProperty    (default=0)                         # Number of times the widget has been used
    url_bak = db.StringProperty     ()                                  # URL saved
    url_got = db.DateTimeProperty   ()                                  # Date the URL was last refreshed
    url_etag = db.TextProperty      ()                                  # ETag for the URL
    url_src = db.TextProperty       ()                                  # Contents of the URL
    output  = db.TextProperty       ()                                  # Actual output

    def update(self):
        # Refresh the URL if it's the first time, or if the target refresh date is past
        if not self.url_bak or self.url_bak != self.url or self.url_got + datetime.timedelta(hours=self.refresh) < NOW:
            try:
                result = urlfetch.fetch(self.url)
                logging.info('Refreshing %s. Status = %d' %  (self.url, result.status_code))
                if result.status_code == 200:
                    self.url_bak = self.url
                    self.url_src = result.content.decode('utf8')
                    self.url_got = NOW
            except:
                logging.info('Refreshing %s. Failed' % self.url)

        # Parse the URL
        output = [ self.header ]
        soup = BeautifulSoup(self.url_src)
        for element in islice(select(soup, self.loop), 0, self.count or MAX_COUNT):
            def replace_selectors(matchobj):
                val = select(element, matchobj.group(1))
                return val and val[0].string or ''
            body = re.sub(r'\{\{(.*?)\}\}', replace_selectors, self.body)
            output.append(body)
        output.append(self.footer)
        self.output = ''.join(output)
        self.put()
        return self

class ListPage(webapp.RequestHandler):
    def get(self):
        recent = Widget.all().order('-updated').fetch(100)
        self.response.out.write(template.render('widget-list.html', dict(locals().items() + globals().items())))

class CreatePage(webapp.RequestHandler):
    def get(self):
        '''Display a blank widget creation page'''
        self.response.out.write(template.render('widget-form.html', dict(locals().items() + globals().items())))

    def post(self):
        '''Create a new widget and redirect to that widget's page'''
        widget, errors = model_from_form(Widget, self.request)
        if not errors:
            widget.put()
            self.redirect('/edit/' + str(widget.key().id()) + '/')
        else:
            self.response.out.write(repr(errors))

class EditPage(webapp.RequestHandler):
    def get(self, key):
        widget = Widget.get_by_id(long(key))
        self.response.out.write(template.render('widget-form.html', dict(locals().items() + globals().items())))

    def post(self, key):
        '''Update the existing widget and render the widget'''
        widget, errors = model_from_form(Widget.get_by_id(long(key)), self.request)
        if not errors:
            widget.update()
            self.redirect('/preview/' + str(widget.key().id()) + '/')
        else:
            self.response.out.write(repr(errors))

class PreviewPage(webapp.RequestHandler):
    def get(self, key):
        widget = Widget.get_by_id(long(key)).update()
        self.response.out.write(template.render('widget-preview.html', dict(locals().items() + globals().items())))

class DeletePage(webapp.RequestHandler):
    def post(self, key):
        Widget.get_by_id(long(key)).delete()
        self.redirect('/')

class WidgetPage(webapp.RequestHandler):
    def get(self, key):
        self.response.out.write(Widget.get_by_id(long(key)).output)
        
class ScriptPage(webapp.RequestHandler):
    def get(self, key):
        output = Widget.get_by_id(long(key)).output
        self.response.out.write(template.render('widget-script.js', dict(locals().items() + globals().items())))
        
application = webapp.WSGIApplication([
        ('/',               ListPage),          # GETs Widgets dashboard
        ('/create/',        CreatePage),        # GET displays a blank widget form, POST creates a new widget and redirects to widget/id
        ('/edit/(\d+)/',    EditPage),          # GET displays an editable form, POST updates the widget
        ('/preview/(\d+)/', PreviewPage),
        ('/delete/(\d+)/',  DeletePage),        # GET confirms deletion, POST deletes the widget and redirects to list page
        ('/widget/(\d+)/',  WidgetPage),        # GET generates IFrame content
        ('/script/(\d+)/',  ScriptPage),        # GET generates script content
    ],
    debug=True)
wsgiref.handlers.CGIHandler().run(application)
