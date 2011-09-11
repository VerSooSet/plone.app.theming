import urllib
import os.path
import json

from zope.component import getMultiAdapter
from zope.site.hooks import getSite
from zope.publisher.browser import BrowserView
from zope.i18n import translate

from plone.resource.interfaces import IResourceDirectory

from plone.app.theming.interfaces import _

from AccessControl import Unauthorized
from OFS.Image import File, Image
from zExceptions import NotFound
from Products.Five.browser.decode import processInputs
from Products.CMFCore.utils import getToolByName

IMAGE_EXTENSIONS = frozenset(['png', 'gif', 'jpg', 'jpeg'])
EXTENSIONS_WITH_ICONS = frozenset([
    'aac', 'avi', 'bmp', 'chm', 'css', 'dll', 'doc', 'fla',
    'gif', 'htm', 'html', 'ini', 'jar', 'jpeg', 'jpg', 'js',
    'lasso', 'mdb', 'mov', 'mp3', 'mpg', 'pdf', 'php', 'png',
    'ppt', 'py', 'rb', 'real', 'reg', 'rtf', 'sql', 'swf', 'txt',
    'vbs', 'wav', 'wma', 'wmv', 'xls', 'xml', 'xsl', 'zip',
])

RESOURCE_DIRECTORY = "++resource++plone.app.theming.editor/filemanager"

class FileManager(BrowserView):

    resourceType = 'theme'

    def __call__(self):
        self.setup()
        form = self.request.form

        # AJAX methods called by the file manager
        if 'mode' in form:
            mode = form['mode']
            
            response = {'Error:': 'Unknown request', 'Code': -1}
            textareaWrap = False

            if mode == u'getfolder':
                response = self.getFolder(
                                path=urllib.unquote(form['path']),
                                getSizes=form.get('getsizes', 'false') == 'true',
                            )
            elif mode == u'getinfo':
                response = self.getInfo(
                                path=urllib.unquote(form['path']),
                                getSize=form.get('getsize', 'false') == 'true',
                            )
            elif mode == u'addfolder':
                response = self.addFolder(
                                path=urllib.unquote(form['path']),
                                name=urllib.unquote(form['name']),
                            )
            elif mode == u'add':
                textareaWrap = True
                response = self.add(
                                path=urllib.unquote(form['currentpath']),
                                newfile=form['newfile'],
                            )
            elif mode == u'addnew':
                response = self.addNew(
                                path=urllib.unquote(form['path']),
                                name=urllib.unquote(form['name']),
                            )
            elif mode == u'rename':
                response = self.rename(
                                path=urllib.unquote(form['old']),
                                newName=urllib.unquote(form['new']),
                            )
            elif mode == u'delete':
                response = self.delete(
                                path=urllib.unquote(form['path']),
                            )
            elif mode == u'download':
                return self.download(
                                path=urllib.unquote(form['path']),
                            )
            
            if textareaWrap:
                self.request.response.setHeader('Content-Type', 'text/html')
                return "<textarea>%s</textarea>" % json.dumps(response)
            else:
                self.request.response.setHeader('Content-Type', 'application/json')
                return json.dumps(response)
        
        # Rendering the view
        else:
            if self.update():
                # Evil hack to deal with the lack of implicit acquisition from
                # resource directories
                self.context = getSite()
                return self.index()
            return ''
    
    def setup(self):
        self.request.response.setHeader('X-Theme-Disabled', '1')
        processInputs(self.request)
        
        self.resourceDirectory = self.context
        self.name = self.resourceDirectory.__name__

        self.portalUrl = getToolByName(self.context, 'portal_url')()
    
    def update(self):
        fileConnector = "%s/++%s++%s/@@theming-controlpanel-filemanager" % (self.portalUrl, self.resourceType, self.name,)
        pathPrefix = "%s/%s/" % (self.portalUrl, RESOURCE_DIRECTORY,)

        self.filemanagerConfiguration = """\
var defaultViewMode = 'grid';
var autoload = true;
var showFullPath = false;
var browseOnly = false;
var fileRoot = '/';
var showThumbs = true;
var imagesExt = ['jpg', 'jpeg', 'gif', 'png'];
var capabilities = new Array('select', 'download', 'rename', 'delete');
var fileConnector = '%s';
var pathPrefix = '%s';
""" % (fileConnector, pathPrefix)

        return True
    
    def authorize(self):
        authenticator = getMultiAdapter((self.context, self.request), name=u"authenticator")
        if not authenticator.verify():
            raise Unauthorized
    
    
    # AJAX responses
    def getFolder(self, path, getSizes=False):
        """Returns a dict of file and folder objects representing the
        contents of the given directory (indicated by a "path" parameter). The
        values are dicts as returned by getInfo().

        A boolean parameter "getsizes" indicates whether image dimensions
        should be returned for each item. Folders should always be returned
        before files.

        Optionally a "type" parameter can be specified to restrict returned
        files (depending on the connector). If a "type" parameter is given for
        the HTML document, the same parameter value is reused and passed
        to getFolder(). This can be used for example to only show image files
        in a file system tree.
        """


        folders = []
        files = []

        path = self.normalizePath(path)
        folder = self.getObject(path)

        for name in folder.listDirectory():
            if IResourceDirectory.providedBy(folder[name]):
                folders.append(self.getInfo(path="%s/%s/" % (path, name), getSize=getSizes))
            else:
                files.append(self.getInfo(path="%s/%s" % (path, name), getSize=getSizes))
        
        return folders + files
        
    def getInfo(self, path, getSize=False):
        """ Returns information about a single file. Requests
        with mode "getinfo" will include an additional parameter, "path",
        indicating which file to inspect. A boolean parameter "getsize"
        indicates whether the dimensions of the file (if an image) should be
        returned.
        """
        
        path = self.normalizePath(path)
        obj = self.getObject(path)

        filename = obj.__name__
        error = ''
        errorCode = 0

        properties = {
            'Date Created': None,
            'Date Modified': None,
        }

        if isinstance(obj, File):
            properties['Date Created'] = obj.created().strftime('%c')
            properties['Date Modified'] = obj.modified().strftime('%c')
            properties['Size'] = obj.get_size()

        fileType = 'txt'

        siteUrl = self.portalUrl
        themeName = self.resourceDirectory.__name__

        preview = "%s/%s/images/fileicons/default.png" % (siteUrl, RESOURCE_DIRECTORY,)

        if IResourceDirectory.providedBy(obj):
            preview = "%s/%s/images/fileicons/_Open.png" % (siteUrl, RESOURCE_DIRECTORY,)
            fileType = 'dir'
            path = path + '/'
        else:
            basename, ext = os.path.splitext(filename)
            filetype = ext[1:]
            if filetype in IMAGE_EXTENSIONS:
                preview = '%s/++%s++%s/%s' % (siteUrl, self.resourceType, themeName, path)
            elif filetype in EXTENSIONS_WITH_ICONS:
                preview = "%s/%s/images/fileicons/%s.png" % (siteUrl, RESOURCE_DIRECTORY, filetype,)
            
        if getSize and isinstance(obj, Image):
            properties['Height'] = obj.height
            properties['Width'] = obj.width
        
        return {
            'Path': path,
            'Filename': filename,
            'File Type': fileType,
            'Preview': preview,
            'Properties': properties,
            'Error': error,
            'Code': errorCode,
        }
    
    def addFolder(self, path, name):
        """The addfolder method creates a new directory on the server within
        the given path.
        """

        parent = self.getObject(path)
        parent.makeDirectory(name)

        return {
            'Parent': path,
            'Name': name,
            'Error': '',
            'Code': 0,
        }
    
    def add(self, path, newfile):
        """The add method adds the uploaded file to the specified path. Unlike
        the other methods, this method must return its JSON response wrapped in
        an HTML <textarea>, so the MIME type of the response is text/html
        instead of text/plain. The upload form in the File Manager passes the
        current path as a POST param along with the uploaded file. The response
        includes the path as well as the name used to store the file. The
        uploaded file's name should be safe to use as a path component in a
        URL, so URL-encoded at a minimum.
        """
        
        parentPath = self.normalizePath(path)
    
        error = ''
        code = 0
            
        name = newfile.filename
        newPath = u"%s/%s" % (parentPath, name,)

        parent = self.getObject(parentPath)
        if name in parent:
            error = translate(_(u'filemanager_error_file_exists', default=u"File already exists."), context=self.request)
            code = 1
        else:
            try:
                self.resourceDirectory.writeFile(newPath.encode('utf-8'), newfile)
            except (ValueError,):
                error = translate(_(u'filemanager_error_file_invalid', default=u"Could not read file."), context=self.request)
                code = 1
        
        return {
            "Path": path,
            "Name": name,
            "Error": error,
            "Code": code,
        }
    
    def addNew(self, path, name):
        """Add a new empty file in the given directory
        """
        
        error = ''
        code = 0

        parentPath = self.normalizePath(path)
        newPath = u"%s/%s" % (parentPath, name,)

        parent = self.getObject(parentPath)
        if name in parent:
            error = translate(_(u'filemanager_error_file_exists', default=u"File already exists."), context=self.request)
            code = 1
        else:
            self.resourceDirectory.writeFile(newPath.encode('utf-8'), '')

        return {
            "Parent": path,
            "Name": name,
            "Error": error,
            "Code": code,
        }


    def rename(self, path, newName):
        """The rename method renames the item at the path given in the "old"
        parameter with the name given in the "new" parameter and returns an
        object indicating the results of that action.
        """

        npath = self.normalizePath(path)
        oldPath = newPath = '/'.join(npath.split('/')[:-1])
        oldName = npath.split('/')[-1]
        
        parent = self.getObject(oldPath)
        parent.renameFile(oldName, newName)

        return {
            "Old Path": oldPath,
            "Old Name": oldName,
            "New Path": newPath, 
            "New Name": newName,
            'Error': '',
            'Code': 0,
        }

    def delete(self, path):
        """The delete method deletes the item at the given path.
        """
        
        npath = self.normalizePath(path)
        parentPath = '/'.join(npath.split('/')[:-1])
        name = npath.split('/')[-1]

        parent = self.getObject(parentPath)
        del parent[name]

        return {
            'Path': path,
            'Error': '',
            'Code': 0,
        }

    def download(self, path):
        """The download method serves the requested file to the user.
        """

        npath = self.normalizePath(path)
        parentPath = '/'.join(npath.split('/')[:-1])
        name = npath.split('/')[-1].encode('utf-8')

        parent = self.getObject(parentPath)

        self.request.response.setHeader('Content-Type', 'application/octet-stream')
        self.request.response.setHeader('Content-Disposition', 'attachment; filename="%s"' % name)

        # TODO: Use streams here if we can
        return parent.readFile(name)

    # AJAX helper methods
    
    def normalizePath(self, path):
        if path.startswith('/'):
            path = path[1:]
        if path.endswith('/'):
            path = path[:-1]
        return path

    def getObject(self, path):
        path = self.normalizePath(path)
        if not path:
            return self.resourceDirectory
        try:
            return self.resourceDirectory[path]
        except (KeyError, NotFound,):
            raise KeyError(path)