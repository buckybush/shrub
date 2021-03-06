import os
import logging
import urllib
import cgi
import datetime

from google.appengine.ext import webapp
from google.appengine.runtime import DeadlineExceededError

from mako.template import Template
from mako.lookup import TemplateLookup

import shrub.utils
import shrub.gae_utils
from shrub.file import S3File
from shrub.s3 import S3

from app.controllers import base
from app.controllers import tape

from shrub import feeds

class DefaultPage(base.BasePage):
	"""Home page"""

	def get(self):
		search = self.request.get('q')
		if search:
			self.redirect("/" + search)
			return

		self.render("index.mako", dict(title="Shrub / Amazon S3 Proxy"))


class S3Page(base.BasePage):
	"""
  Front controller for all S3 style requests (until I figure out how to do more advanced routing). 
  
  Request should be passed off based on their format or response type.
  """
	
	def _get(self):
		format = self.request.get('format', None)
		max_keys = self.request.get('max-keys')
		delimiter = self.request.get('delimiter', '/')
		marker = self.request.get('marker', None)
		prefix = self.request.get('prefix', None)

		cache_key = self.request.url

		bucket_name, prefix_from_request = shrub.gae_utils.parse_gae_request(self.request)
		if prefix is None:
			prefix = prefix_from_request

		if not bucket_name:
			handler = ErrorResponse(self)
			handler.render_error(404)
			return

		if format == 'id3-json':
			s3file = S3File(bucket_name, prefix_from_request)
			tape.ID3Response(self).load_url(s3file.to_url(), 'json', cache_key=cache_key)
			return

		# Make S3 request
		s3response = S3().list(bucket_name, max_keys, prefix, delimiter, marker)

		# If not 2xx, show friendly error page
		if not s3response.ok:
			handler = ErrorResponse(self)
			handler.handle(s3response)
			return

		# If no format use HTML response
		if not format:
			handler = HTMLResponse(self)
			handler.handle(s3response)
			return

		# If truncated with a request format; return 501
		if s3response.is_truncated:
			handler = ErrorResponse(self)
			handler.render_error(501, "There were too many items ( &gt; %s ) in the current bucket to sort and display." % s3response.max_keys)
			return

		# Get handler for format
		if format == 'rss': handler = RSSResponse(self)
		elif format.startswith('xspf'): handler = tape.XSPFResponse(self)
		elif format == 'tape': handler = tape.TapeResponse(self)
		elif format == 'json': handler = JSONResponse(self)
		elif format == 'error': handler = ErrorResponse(self)
		else:
		# If no handler for a format return error page
			handler = ErrorResponse(self)
			handler.render_error(404, "The requested format parameter is unknown.", title="Not found")
			return

		# Render response with handler
		handler.handle(s3response)

	def get(self):
		try:
			self._get()
		except DeadlineExceededError:
			self.response.clear()
			ErrorResponse(self).render_error(500, "The request couldn't be completed in time. Please try again.")


class HTMLResponse(base.BaseResponse):

	def handle(self, s3response):
		files = s3response.files
		path_components = s3response.path_components()
		path_names = s3response.path_components(url_escape=False)
		path = s3response.path
		warning_message = None

		sort = 'name'
		sort_property = 'key'
		sort_asc = True

		if s3response.is_truncated:
			if self.request.get('s', None) is not None:
				warning_message = 'Because the result was truncated, the sort option was ignored.'
		else:
			sort = self.request.get('s', 'name')
			if sort.endswith(':d'): 
				sort_asc = False
				sort = sort[:-2]
			# Change sort aliases
			if sort == 'date': sort_property = 'last_modified'
			elif sort == 'name': sort_property = 'key'
			elif sort == 'size': sort_property = 'size'

		files.sort(cmp=lambda x, y: shrub.utils.file_comparator(x, y, sort_property, sort_asc))

		# Default url options to pass through to links
		url_options = dict()
		max_keys = self.request.get('max-keys', None)
		if max_keys:
			url_options['max-keys'] = max_keys

		next_page_url_options = url_options.copy()
		next_page_url_options['marker'] = s3response.next_marker
		next_page_url = '/%s/?%s' % (path, shrub.utils.params_to_url(next_page_url_options, True))

		# Render response
		template_values = {
			'title': shrub.utils.url_unescape(path),
			'path_names': path_names,
			'path_components': path_components,
			'path': path,
			'sort': sort,
			'sort_asc': sort_asc,
			'url_options': url_options,
			'next_page_url': next_page_url,
			's3response': s3response,
			'warning_message': warning_message
		}

		self.render("list.mako", template_values)


class JSONResponse(base.JSONResponse):

	def handle(self, s3response):
		super(JSONResponse, self).handle(s3response.data)


class RSSResponse(base.BaseResponse):

	def handle(self, s3response):
		files = s3response.files
		path = s3response.path
		
		rss_items = []
		files.sort(cmp=lambda x, y: shrub.utils.file_comparator(x, y, 'last_modified', False))

		for file in files[:50]:
			rss_items.append(file.to_rss_item())

		pub_date = datetime.datetime.now()
		if len(rss_items) > 0:
			pub_date = rss_items[0].pub_date

		title = u'%s (Shrub)' % path
		link = "http://s3hub.appspot.com/%s" % path

		assigns = dict(title=title, description=u'RSS feed for %s' % s3response.url, items=rss_items, link=link, pub_date=pub_date)
		self.render("rss.mako", assigns, 'text/xml;charset=utf-8')


class ErrorResponse(base.BaseResponse):
	"""Handle standard error response."""

	def render_error(self, status_code, error_message=None, title="Error"):
		self.request_handler.response.set_status(status_code)
		self.request_handler.render("error.mako", dict(title=title, s3url=None, status_code=status_code, message=error_message, path=None))

	def handle(self, s3response):
		title = None
		message = None
		url = s3response.url
		request = self.request
		request_url = request.url if request else None

		status_code = s3response.status_code
		error_message = s3response.message

		if status_code == 403:
			title = 'Permission denied'
			message = 'Shrub does not have permission to access this bucket. Shrub can only act on public buckets.'
		elif status_code == 404:
			title = 'Not found'
			message = 'This bucket or folder was not found. Try verifying that it exists.'
		elif status_code in range(400, 500):
			title = 'Client error'
			message = 'There was an error trying to access S3.'
		elif status_code in range(500, 600):
			title = 'Not available. Please try again.'
			message = 'There was an error trying to access S3. Please try again.'
		else:
			title = 'Unknown error'
			message = 'There was an unknown error.'

		if error_message:
			message += ' (%s)' % error_message

		self.request_handler.response.set_status(status_code)
		self.request_handler.render("error.mako", dict(title=title, s3url=url, status_code=status_code, message=message, request_url=request_url))

