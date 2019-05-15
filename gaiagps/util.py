import datetime
import logging
import os
import pytz
import string
import tzlocal

LOG = logging.getLogger(__name__)


ICON_ALIASES = {
    'blue': 'blue-pin-down.png',
    'black': 'black-pin.png',
    'brown': 'brown-pin.png',
    'gray': 'gray-pin.png',
    'green': 'green-pin.png',
    'orange': 'orange-pin.png',
    'purple': 'purple-pin.png',
    'red': 'red-pin-down.png',
    'white': 'white-pin.png',
    'yellow': 'yellow-pin.png',
    'airport': 'airport-24.png',
    'bicycle': 'bicycle-24.png',
    'building': 'building-24.png',
    'cafe': 'cafe-24.png',
    'camera': 'camera-24.png',
    'campsite': 'campsite-24.png',
    'car': 'car-24.png',
    'cemetary': 'cemetary-24.png',
    'chemist': 'chemist-24.png',
    'circle': 'circle-24.png',
    'city': 'city-24.png',
    'dam': 'dam-24.png',
    'disability': 'disability-24.png',
    'dog-park': 'dog-park-24.png',
    'emergency-telephone': 'emergency-telephone-24.png',
    'fast-food': 'fast-food-24.png',
    'fire-station': 'fire-station-24.png',
    'fuel': 'fuel-24.png',
    'garden': 'garden-24.png',
    'golf': 'golf-24.png',
    'harbor': 'harbor-24.png',
    'heart': 'heart-24.png',
    'heliport': 'heliport-24.png',
    'hospital': 'hospital-24.png',
    'lighthouse': 'lighthouse-24.png',
    'lodging': 'lodging-24.png',
    'logging': 'logging-24.png',
    'minefield': 'minefield-24.png',
    'mobilephone': 'mobilephone-24.png',
    'oil-well': 'oil-well-24.png',
    'park': 'park-24.png',
    'parking': 'parking-24.png',
    'pitch': 'pitch-24.png',
    'playground': 'playground-24.png',
    'polling-place': 'polling-place-24.png',
    'prison': 'prison-24.png',
    'rail': 'rail-24.png',
    'restaurant': 'restaurant-24.png',
    'skiing': 'skiing-24.png',
    'square': 'square-24.png',
    'star': 'star-24.png',
    'suitcase': 'suitcase-24.png',
    'swimming': 'swimming-24.png',
    'toilets': 'toilets-24.png',
    'triangle': 'triangle-24.png',
    'water': 'water-24.png',
    'wetland': 'wetland-24.png',
}


def date_parse(thing):
    """Parse a local datetime from a thing with a datestamp.

    This attempts to find a datestamp in an object and parse it for
    use in the local timezone.

    Something like this is required::

      {'id': '1234', 'title': 'Foo', 'time_created': '2019-01-01T10:11:12Z'}

    :param thing: A raw object from the API
    :type thing: dict
    :returns: A localized tz-aware `datetime` or None if no datestamp is found.
    :rtype: :class:`datetime.datetime`
    """
    ds = thing.get('time_created') or thing['properties'].get('time_created')
    if not ds:
        return None

    if 'Z' in ds:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%SZ')
    elif '.' in ds:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%S.%f')
    else:
        dt = datetime.datetime.strptime(ds, '%Y-%m-%dT%H:%M:%S')

    dt = pytz.utc.localize(dt)
    return dt.astimezone(tzlocal.get_localzone())


def datefmt(thing):
    """Nicely format a thing with a datestamp.

    See :func:`~date_parse` for more information.

    :param thing: A ``dict`` raw object from the API.
    :type thing: dict
    :returns: A nicely-formatted date string, or ``'?'`` if none is found
              or is parseable
    :rtype: `str`
    """
    localdt = date_parse(thing)
    if localdt:
        return localdt.strftime('%d %b %Y %H:%M:%S')
    else:
        return '?'


def make_waypoint(name, lat, lon, alt=0, notes='', icon=''):
    """Make a raw waypoint object.

    This returns an object suitable for sending to the API.

    :param lat: A ``float`` representing latitude
    :type lat: float
    :param lon: A ``float`` representing longitude
    :type lon: float
    :param alt: A ``float`` representing altitude in meters
    :type alt: float
    :param notes: A ``str`` representing the notes field
    :type notes: str
    :param icon: A ``str`` representing the icon (one of the values
                 supported by gaiagps, for example ``blue-pin-down.png``)
    :type icon: str
    :returns: A ``dict`` object
    :rtype: `dict`
    """
    return {
        'type': 'Feature',
        'properties': {
            'title': name,
            'notes': notes,
            'icon': icon,
        },
        'geometry': {
            'type': 'Point',
            'coordinates': [lon, lat, alt],
        },
    }


def make_folder(name):
    """Make a folder object.

    This returns an object suitable for sending to the API.

    :param name: A ``str`` representing the folder name
    :type name: str
    :returns: A ``dict`` object
    :rtype: `dict`
    """
    return {'title': name}


def make_tree(folders):
    """Creates a hierarchical structure of folders.

    This takes a flat list of folder objects and returns
    a nested ``dict`` with subfolders inside their parent's
    ``subfolders`` key. A new root folder structure is at the
    top, with a name of ``/``.

    :param folders: A flat ``list`` of folders like you get from
                    :func:`~gaiagps.apiclient.GaiaClient.list_objects`
    :type folders: list
    :returns: A hierarchical ``dict`` of folders
    :rtype: `dict`
    """
    folders_by_id = {folder['id']: folder
                     for folder in folders}
    root = {
        'properties': {
            'name': '/',
            'waypoints': {},
            'tracks': {},
        },
    }

    for folder in folders:
        if folder.get('parent'):
            parent = folders_by_id[folder['parent']]
        else:
            parent = root

        parent.setdefault('subfolders', {})
        parent['subfolders'][folder['id']] = folder

    return root


def resolve_tree(client, folder):
    """Walk the tree and flesh out folders with waypoint/track data.

    This takes a hierarchical folder tree from :func:`make_tree` and
    replaces the folder descriptions with full definitions, as you
    would get from :func:`~gaiagps.apiclient.GaiaClient.get_object`.

    :param client: An instance of :class:`~gaiagps.apiclient.GaiaClient`
    :type client: GaiaClient
    :param folder: A root folder of a hierarchical tree from
                   :func:`make_tree`
    :type folder: dict
    :returns: A hierarchical tree of full folder definitions.
    :rtype: `dict`
    """

    if 'id' in folder:
        LOG.debug('Resolving %s' % folder['id'])
        updated = client.get_object('folder', id_=folder['id'])
        subf = folder.get('subfolders', {})
        folder.clear()
        folder.update(updated)
        folder['subfolders'] = subf
    else:
        # This is the fake root folder
        LOG.debug('Resolving root folder (by force)')
        folder['properties']['waypoints'] = [
            w for w in client.list_objects('waypoint')
            if w['folder'] == '']
        folder['properties']['tracks'] = [
            t for t in client.list_objects('track')
            if t['folder'] == '']

    for subfolder in folder.get('subfolders', {}).values():
        LOG.debug('Descending into %s' % subfolder['id'])
        resolve_tree(client, subfolder)

    return folder


def title_sort(iterable):
    """Return a sorted list of items by title.

    :param iterable: Items to sort
    :returns: Items in title sort order
    """
    return sorted(iterable, key=lambda e: e['title'])


def name_sort(iterable):
    """Return a sorted list of items by name.

    :param iterable: Items to sort
    :returns: Items in name sort order
    """
    return sorted(iterable, key=lambda e: e.get('name', ''))


def pprint_folder(folder, indent=0, long=False):
    """Print a tree of folder contents.

    This prints a pseudo-filesystem view of a folder tree to the
    console.

    :param folder: A folder tree root from :func:`resolve_tree`
    :type folder: dict
    :param indent: Number of spaces to indent the first level
    :type indent: int
    """
    midchild = b'\xe2\x94\x9c\xe2\x94\x80\xe2\x94\x80'.decode()
    lastchild = b'\xe2\x94\x94\xe2\x94\x80\xe2\x94\x80'.decode()

    def format_thing(thing):
        fields = []
        if long:
            fields.append(datefmt(thing))
        fields.append(thing.get('title') or
                      thing.get('properties')['name'])
        return ' '.join(fields)

    if indent == 0:
        print('/')

    pfx = (' ' * indent) + midchild
    for subf in name_sort(folder.get('subfolders', {}).values()):
        print('%s %s/' % (pfx, format_thing(subf)))
        pprint_folder(subf, indent=indent + 4, long=long)

    children = (
        [('W', w) for w in title_sort(
            folder['properties']['waypoints'])] +
        [('T', t) for t in title_sort(
            folder['properties']['tracks'])])

    while children:
        char, child = children.pop(0)
        if children:
            pfx = (' ' * indent) + midchild
        else:
            pfx = (' ' * indent) + lastchild
        print('%s [%s] %s' % (pfx, char, format_thing(child)))


def validate_lat(lat):
    """Validate and normalize a latitude

    Only decimal degrees is supported

    :param lat: A latitude string
    :type lat: str
    :returns: A latitude
    :rtype: `float`
    :raises ValueError: If the latitude is not parseable or within constraints
    """
    try:
        lat = float(lat)
    except ValueError:
        raise ValueError('Latitude must be in decimal degree format')

    if lat < -90 or lat > 90:
        raise ValueError('Latitude must be between -90 and 90')

    return lat


def validate_lon(lon):
    """Validate and normalize a longitude

    Only decimal degrees is supported

    :param lon: A longitude string
    :type lon: str
    :returns: A longitude
    :rtype: `float`
    :raises ValueError: If the longitude is not parseable or within constraints
    """
    try:
        lon = float(lon)
    except ValueError:
        raise ValueError('Longitude must be in decimal degree format')

    if lon < -180 or lon > 180:
        raise ValueError('Longitude must be between -180 and 180')

    return lon


def validate_alt(alt):
    """Validate and normalize an altitude

    Only meters are supported

    :param alt: An altitude string
    :type alt: str
    :returns: An altitude
    :rtype: `float`
    :raises ValueError: If the altitude is not parseable or within constraints
    """
    try:
        alt = int(alt)
    except ValueError:
        raise ValueError('Altitude must be a positive integer number of '
                         'meters')

    if alt < 0:
        raise ValueError('Altitude must be positive')

    return alt


def is_id(idstr):
    """Detect if a string is likely an API identifier

    :param idstr: An ID string to be examined
    :type idstr: str
    :returns: ``True`` if the string is an identifier, ``False`` otherwise
    :rtype: `bool`
    """
    return (len(idstr) in (36, 32) and
            all(c in string.hexdigits + '-' for c in idstr))


def get_editor():
    """Return a path to an editor command, if possible.

    :returns: Path to an editor command or None if one is not found
    """

    editor = os.environ.get('EDITOR', '/usr/bin/editor')
    if editor and os.access(editor, os.X_OK):
        return editor
