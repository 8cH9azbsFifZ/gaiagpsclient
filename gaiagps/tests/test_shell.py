import contextlib
import copy
import io
import mock
import os
import pprint
import shlex
import unittest

from gaiagps import apiclient
from gaiagps import shell
from gaiagps import util


client = apiclient.GaiaClient


class FakeOutput(io.StringIO):
    def fileno(self):
        return -1


class FakeClient(object):
    FOLDERS = [
        {'id': '101', 'folder': None, 'title': 'folder1'},
        {'id': '102', 'folder': None, 'title': 'folder2'},
        {'id': '103', 'folder': '101', 'title': 'subfolder'},
        {'id': '104', 'folder': None, 'title': 'emptyfolder'},
        ]
    WAYPOINTS = [
        {'id': '001', 'folder': None, 'title': 'wpt1'},
        {'id': '002', 'folder': '101', 'title': 'wpt2', 'deleted': True},
        {'id': '003', 'folder': '103', 'title': 'wpt3',
         'properties': {'time_created': '2015-10-21T23:29:00Z'}},
    ]
    TRACKS = [
        {'id': '201', 'folder': None, 'title': 'trk1'},
        {'id': '202', 'folder': '102', 'title': 'trk2'},
    ]

    s = None

    def __init__(self, *a, **k):
        pass

    def list_objects(self, objtype, archived=True):
        def add_props(l):
            return [dict(d, properties=d.get('properties', {}),
                         deleted=d.get('deleted', False))
                    for d in l
                    if archived or d.get('deleted', False) is False]

        if objtype == 'waypoint':
            return add_props(self.WAYPOINTS)
        elif objtype == 'track':
            return add_props(self.TRACKS)
        elif objtype == 'folder':
            r = []
            for f in self.FOLDERS:
                r.append(dict(f,
                              maps=[],
                              waypoints=[w['id'] for w in self.WAYPOINTS
                                         if w['folder'] == f['id']],
                              tracks=[t['id'] for t in self.TRACKS
                                      if t['folder'] == f['id']],
                              children=[f['id'] for f in self.FOLDERS
                                        if f['folder'] == f['id']]))
            return r
        else:
            raise Exception('Invalid type %s' % objtype)

    def get_object(self, objtype, name=None, id_=None, fmt=None):
        if name:
            key = 'title'
            value = name
        else:
            key = 'id'
            value = id_

        lst = getattr(self, objtype.upper() + 'S')
        obj = dict(apiclient.find(lst, key, value))

        if fmt is not None:
            return 'object %s format %s' % (obj['id'], fmt)

        key = 'name' if objtype == 'folder' else 'title'
        obj.setdefault('properties', {})
        obj['properties'][key] = obj.pop('title')
        if objtype == 'waypoint':
            obj['geometry'] = {'coordinates': [-122.0, 45.5, 123]}
        elif objtype == 'folder':
            obj['properties']['waypoints'] = [
                w for w in self.WAYPOINTS
                if w['folder'] == obj['id']]
            obj['properties']['tracks'] = [
                w for w in self.TRACKS
                if w['folder'] == obj['id']]
        return obj

    def add_object_to_folder(self, folderid, objtype, objid):
        raise NotImplementedError('Mock me')

    def remove_object_from_folder(self, folderid, objtype, objid):
        raise NotImplementedError('Mock me')

    def delete_object(self, objtype, id_):
        raise NotImplementedError('Mock me')

    def put_object(self, objtype, objdata):
        raise NotImplementedError('Mock me')

    def create_object(self, objtype, objdata):
        raise NotImplementedError('Mock me')

    def upload_file(self, filename):
        raise NotImplementedError('Mock me')

    def set_objects_archive(self, objtype, ids, archive):
        raise NotImplementedError('Mock me')

    def test_auth(self):
        raise NotImplementedError('Mock me')


@contextlib.contextmanager
def fake_cookiejar():
    yield None


@mock.patch('gaiagps.shell.cookiejar', new=fake_cookiejar)
@mock.patch.object(apiclient, 'GaiaClient', new=FakeClient)
class TestShellUnit(unittest.TestCase):
    def _run(self, cmdline, expect_fail=False):
        out = FakeOutput()
        with mock.patch.multiple('sys', stdout=out, stderr=out, stdin=out):
            rc = shell.main(shlex.split(cmdline))
        print(out.getvalue())
        if not expect_fail:
            self.assertEqual(0, rc)
        else:
            self.assertNotEqual(0, rc)
        return out.getvalue()

    def test_first_run(self):
        out = self._run('', expect_fail=True)
        self.assertIn('usage:', out)

    def test_waypoint_list_by_id(self):
        out = self._run('waypoint list --by-id')
        self.assertIn('001', out)
        self.assertIn('wpt2', out)

    def test_list_wpt(self):
        out = self._run('waypoint list')
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)
        self.assertIn('wpt3', out)
        self.assertIn('folder1', out)
        self.assertIn('subfolder', out)
        self.assertNotIn('folder2', out)

    def test_list_trk(self):
        out = self._run('track list')
        self.assertIn('trk1', out)
        self.assertIn('trk2', out)
        self.assertIn('folder2', out)
        self.assertNotIn('folder1', out)
        self.assertNotIn('subfolder', out)

    def test_list_match(self):
        out = self._run('waypoint list --match w.*2')
        self.assertIn('wpt2', out)
        self.assertNotIn('wpt1', out)

    def test_list_match_date(self):
        out = self._run('waypoint list --match-date 2019-01-01')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertNotIn('wpt3', out)

        out = self._run('waypoint list --match-date 2015-10-21')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        out = self._run('waypoint list --match-date 2015-10-21:2015-10-22')
        self.assertNotIn('wpt1', out)
        self.assertNotIn('wpt2', out)
        self.assertIn('wpt3', out)

        out = self._run('waypoint list --match-date foo',
                        expect_fail=True)
        out = self._run('waypoint list --match-date 2015-10-21:foo',
                        expect_fail=True)

    @mock.patch.object(FakeClient, 'list_objects')
    def test_list_archived_include_logic(self, mock_list):
        self._run('waypoint list')
        mock_list.assert_called_once_with('waypoint', archived=True)

        mock_list.reset_mock()
        self._run('waypoint list --archived=no')
        mock_list.assert_called_once_with('waypoint', archived=False)

        mock_list.reset_mock()
        self._run('waypoint list --archived=yes')
        mock_list.assert_called_once_with('waypoint', archived=True)

        mock_list.reset_mock()
        self._run('waypoint list --archived=foo',
                  expect_fail=True)
        mock_list.assert_not_called()

    def test_list_archived(self):
        out = self._run('waypoint list')
        self.assertIn('wpt1', out)
        self.assertIn('wpt2', out)

        out = self._run('waypoint list --archived=y')
        self.assertNotIn('wpt1', out)
        self.assertIn('wpt2', out)

        out = self._run('waypoint list --archived=n')
        self.assertIn('wpt1', out)
        self.assertNotIn('wpt2', out)

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move(self, mock_add, verbose=False, dry=False):
        out = self._run('%s waypoint move wpt1 wpt2 folder2 %s' % (
            verbose and '--verbose' or '',
            dry and '--dry-run' or ''))
        if dry:
            mock_add.assert_not_called()
        else:
            mock_add.assert_has_calls([mock.call('102', 'waypoint', '001'),
                                       mock.call('102', 'waypoint', '002')])
        if verbose:
            self.assertIn('wpt1', out)
            self.assertIn('wpt2', out)
            self.assertIn('folder2', out)
            self.assertNotIn('wpt3', out)
            self.assertNotIn('folder1', out)
            self.assertNotIn('subfolder', out)
        elif dry:
            self.assertIn('Dry run', out)
        else:
            self.assertEqual('', out)

    def test_move_verbose(self):
        self.test_move(verbose=True)

    def test_move_dry_run(self):
        self.test_move(verbose=True, dry=True)

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match(self, mock_add):
        self._run('waypoint move --match w.*2 folder2')
        mock_add.assert_has_calls([mock.call('102', 'waypoint', '002')])

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_date(self, mock_add):
        self._run('waypoint move --match-date 2015-10-21 folder2')
        mock_add.assert_called_once_with('102', 'waypoint', '003')

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_none(self, mock_add):
        out = self._run('waypoint move --match-date 2019-01-01 folder2')
        self.assertIn('', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_match_ambiguous(self, mock_add):
        out = self._run('waypoint move folder2',
                        expect_fail=True)
        self.assertIn('Specify', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_move_to_nonexistent_folder(self, mock_add):
        out = self._run('waypoint move wpt1 wpt2 foobar',
                        expect_fail=True)
        self.assertIn('foobar not found', out)
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'remove_object_from_folder')
    def test_move_to_root(self, mock_remove):
        out = self._run('waypoint move wpt1 wpt2 /')
        mock_remove.assert_has_calls([mock.call('101', 'waypoint', '002')])
        self.assertIn('\'wpt1\' is already at root', out)

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove(self, mock_delete, dry=False):
        out = self._run('waypoint remove wpt1 wpt2 %s' % (
            dry and '--dry-run' or ''))
        if dry:
            self.assertIn('Dry run', out)
            mock_delete.assert_not_called()
        else:
            self.assertEqual('', out)
            mock_delete.assert_has_calls([mock.call('waypoint', '001'),
                                          mock.call('waypoint', '002')])

    def test_remove_dry_run(self):
        self.test_remove(dry=True)

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_match_verbose(self, mock_delete):
        out = self._run('--verbose waypoint remove --match w.*2')
        self.assertIn('Removing waypoint \'wpt2\'', out)
        mock_delete.assert_has_calls([mock.call('waypoint', '002')])

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_missing(self, mock_delete):
        out = self._run('--verbose waypoint remove wpt7',
                        expect_fail=True)
        self.assertIn('not found', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_empty(self, mock_delete):
        out = self._run('--verbose folder remove emptyfolder')
        self.assertIn('Removing', out)
        mock_delete.assert_called_once_with('folder', '104')

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty(self, mock_delete):
        out = self._run('--verbose folder remove folder1')
        self.assertIn('skipping', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty_force(self, mock_delete):
        out = self._run('--verbose folder remove --force folder1')
        self.assertIn('Warning', out)
        mock_delete.assert_called_once_with('folder', '101')

    @mock.patch('builtins.input')
    @mock.patch('os.isatty', return_value=True)
    @mock.patch.object(FakeClient, 'delete_object')
    def test_remove_folder_nonempty_prompt(self, mock_delete, mock_tty,
                                           mock_input):
        mock_input.return_value = ''
        self._run('--verbose folder remove folder1')
        mock_delete.assert_not_called()

        mock_input.return_value = 'y'
        self._run('--verbose folder remove folder1')
        mock_delete.assert_called_once_with('folder', '101')

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_waypoint(self, mock_put, dry=False):
        out = self._run(
            '--verbose waypoint rename wpt2 wpt7 %s' % (
                dry and '--dry-run' or ''))
        self.assertIn('Renaming', out)
        new_wpt = {'id': '002', 'folder': '101',
                   'properties': {'title': 'wpt7'},
                   'geometry': {'coordinates': [-122.0, 45.5, 123]},
                   'deleted': True}
        if dry:
            mock_put.assert_not_called()
        else:
            mock_put.assert_called_once_with('waypoint', new_wpt)

    def test_rename_dry_run(self):
        self.test_rename_waypoint(dry=True)

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_track(self, mock_put):
        out = self._run('--verbose track rename trk2 trk7')
        self.assertIn('Renaming', out)
        new_trk = {'id': '202', 'title': 'trk7'}
        mock_put.assert_called_once_with('track', new_trk)

    @mock.patch.object(FakeClient, 'put_object')
    def test_rename_fail(self, mock_put):
        mock_put.return_value = None
        out = self._run('track rename trk2 trk7',
                        expect_fail=True)
        self.assertIn('Failed to rename', out)

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint(self, mock_create):
        out = self._run('waypoint add foo 1.5 2.6')
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6, 0))

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_dry_run(self, mock_add, mock_create):
        out = self._run('waypoint add --dry-run test 1 2')
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

        out = self._run('waypoint add --dry-run --new-folder foo test 1 2')
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

        out = self._run('waypoint add --dry-run --existing-folder folder1 '
                        'test 1 2')
        self.assertIn('Dry run', out)
        mock_create.assert_not_called()
        mock_add.assert_not_called()

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_with_altitude(self, mock_create):
        out = self._run('waypoint add foo 1.5 2.6 3')
        self.assertEqual('', out)
        mock_create.assert_called_once_with(
            'waypoint',
            util.make_waypoint('foo', 1.5, 2.6, 3))

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_bad_data(self, mock_create):
        out = self._run('waypoint add foo a 2.6',
                        expect_fail=True)
        self.assertIn('Latitude', out)

        out = self._run('waypoint add foo 1.5 a',
                        expect_fail=True)
        self.assertIn('Longitude', out)

        out = self._run('waypoint add foo 1.5 2.6 a',
                        expect_fail=True)
        self.assertIn('Altitude', out)

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_waypoint_failed(self, mock_create):
        mock_create.return_value = None
        out = self._run('waypoint add foo 1.2 2.6',
                        expect_fail=True)
        self.assertIn('Failed to create waypoint', out)

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_new_folder(self, mock_add, mock_create):
        mock_create.side_effect = [
            {'id': '1'},
            {'id': '2', 'properties': {'name': 'folder'}}]
        out = self._run('waypoint add --new-folder bar foo 1.5 2.6')
        self.assertEqual('', out)
        mock_create.assert_has_calls([
            mock.call('waypoint',
                      util.make_waypoint('foo', 1.5, 2.6, 0)),
            mock.call('folder',
                      util.make_folder('bar'))])
        mock_add.assert_called_once_with('2', 'waypoint', '1')

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_waypoint_existing_folder(self, mock_add, mock_create):
        mock_create.side_effect = [
            {'id': '1'},
            {'id': '2', 'properties': {'name': 'folder'}}]
        out = self._run(
            'waypoint add --existing-folder folder1 foo 1.5 2.6')
        self.assertEqual('', out)
        mock_create.assert_has_calls([
            mock.call('waypoint',
                      util.make_waypoint('foo', 1.5, 2.6, 0))])
        mock_add.assert_called_once_with('101', 'waypoint', '1')

    def test_add_waypoint_existing_folder_not_found(self):
        out = self._run('waypoint add --existing-folder bar foo 1.5 2.6',
                        expect_fail=True)
        self.assertIn('not found', out)

    @mock.patch.object(FakeClient, 'upload_file')
    def test_upload(self, mock_upload):
        self._run('upload foo.gpx')
        mock_upload.assert_called_once_with('foo.gpx')

    @mock.patch.object(FakeClient, 'set_objects_archive')
    def _test_archive_waypoint(self, cmd, mock_archive):
        args = [
            'wpt3',
            '--match w.*3',
            '--match-date 2015-10-21',
        ]
        for arg in args:
            mock_archive.reset_mock()
            self._run('waypoint %s %s' % (cmd, arg))
            mock_archive.assert_called_once_with('waypoint', ['003'],
                                                 cmd == 'archive')

    def test_archive_waypoint(self):
        self._test_archive_waypoint('archive')

    def test_unarchive_waypoint(self):
        self._test_archive_waypoint('unarchive')

    @mock.patch.object(FakeClient, 'set_objects_archive')
    def test_archive_fails(self, mock_archive):
        self._run('waypoint archive',
                  expect_fail=True)
        mock_archive.assert_not_called()

        self._run('waypoint archive --match nothing')
        mock_archive.assert_not_called()

    def test_waypoint_coords(self):
        out = self._run('waypoint coords wpt1')
        self.assertEqual('45.500000,-122.000000', out.strip())

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_folder(self, fake_create):
        out = self._run('folder add foo')
        self.assertEqual('', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_dry_run(self, fake_add, fake_create):
        out = self._run('folder add --dry-run foo')
        self.assertIn('Dry run', out)
        fake_create.assert_not_called()
        fake_add.assert_not_called()

        out = self._run('folder add --dry-run --existing-folder folder1 '
                        'foo')
        self.assertIn('Dry run', out)
        fake_create.assert_not_called()
        fake_add.assert_not_called()

    @mock.patch.object(FakeClient, 'create_object')
    def test_add_folder_failed(self, mock_create):
        mock_create.return_value = None
        out = self._run('folder add foo',
                        expect_fail=True)
        self.assertIn('Failed to add folder', out)

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_to_existing(self, fake_add, fake_create):
        fake_create.return_value = {'id': '105'}
        out = self._run('folder add --existing-folder folder1 foo')
        self.assertEqual('', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))
        fake_add.assert_called_once_with('101', 'folder', '105')

    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'add_object_to_folder')
    def test_add_folder_to_existing_fail(self, fake_add, fake_create):
        fake_create.return_value = {'id': '105'}
        fake_add.return_value = None
        out = self._run('folder add --existing-folder folder1 foo',
                        expect_fail=True)
        self.assertIn('failed to add', out)
        fake_create.assert_called_once_with('folder', util.make_folder('foo'))

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_existing_folder(self, mock_delete, mock_put, mock_upload):
        mock_upload.return_value = {'id': '105', 'properties': {
            'name': 'foo.gpx'}}

        folders_copy = copy.deepcopy(FakeClient.FOLDERS)
        folders_copy.append({'id': '105',
                             'title': 'foo.gpx',
                             'folder': None,
                             'properties': {}})

        waypoints_copy = copy.deepcopy(FakeClient.WAYPOINTS)
        waypoints_copy.append({'id': '010', 'folder': '105', 'title': 'wpt8'})
        waypoints_copy.append({'id': '011', 'folder': '105', 'title': 'wpt9'})

        tracks_copy = copy.deepcopy(FakeClient.TRACKS)
        tracks_copy.append({'id': '210', 'folder': '105', 'title': 'trk8'})
        tracks_copy.append({'id': '211', 'folder': '105', 'title': 'trk9'})

        with mock.patch.multiple(FakeClient,
                                 FOLDERS=folders_copy,
                                 WAYPOINTS=waypoints_copy,
                                 TRACKS=tracks_copy):
            self._run('upload --existing-folder folder1 foo.gpx')

        expected = copy.deepcopy(FakeClient.FOLDERS[0])
        expected['children'] = []
        expected['maps'] = []
        expected['waypoints'] = ['002', '010', '011']
        expected['tracks'] = ['210', '211']
        mock_put.assert_called_once_with('folder', expected)
        mock_delete.assert_called_once_with('folder', '105')

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch.object(FakeClient, 'delete_object')
    @mock.patch.object(FakeClient, 'create_object')
    def test_upload_new_folder(self, mock_create, mock_delete, mock_put,
                               mock_upload):
        mock_upload.return_value = {'id': '105', 'properties': {
            'name': 'foo.gpx'}}

        folders_copy = copy.deepcopy(FakeClient.FOLDERS)
        folders_copy.append({'id': '105',
                             'title': 'foo.gpx',
                             'folder': None,
                             'properties': {}})
        folders_copy.append({'id': '106',
                             'title': 'newfolder',
                             'folder': None,
                             'properties': {'name': 'newfolder'}})

        mock_create.return_value = folders_copy[-1]

        waypoints_copy = copy.deepcopy(FakeClient.WAYPOINTS)
        waypoints_copy.append({'id': '010', 'folder': '105', 'title': 'wpt8'})
        waypoints_copy.append({'id': '011', 'folder': '105', 'title': 'wpt9'})

        tracks_copy = copy.deepcopy(FakeClient.TRACKS)
        tracks_copy.append({'id': '210', 'folder': '105', 'title': 'trk8'})
        tracks_copy.append({'id': '211', 'folder': '105', 'title': 'trk9'})

        with mock.patch.multiple(FakeClient,
                                 FOLDERS=folders_copy,
                                 WAYPOINTS=waypoints_copy,
                                 TRACKS=tracks_copy):
            self._run('upload --new-folder newfolder foo.gpx')

        expected = copy.deepcopy(folders_copy[-1])
        expected['children'] = []
        expected['maps'] = []
        expected['waypoints'] = ['010', '011']
        expected['tracks'] = ['210', '211']
        mock_put.assert_called_once_with('folder', expected)
        mock_delete.assert_called_once_with('folder', '105')

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'create_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_new_folder_create_fail(self, mock_delete, mock_create,
                                           mock_upload):
        mock_create.return_value = None
        out = self._run('upload --new-folder foo foo.gpx',
                        expect_fail=True)
        self.assertIn('failed to create folder', out)
        mock_delete.assert_not_called()

    @mock.patch.object(FakeClient, 'upload_file')
    @mock.patch.object(FakeClient, 'put_object')
    @mock.patch.object(FakeClient, 'delete_object')
    def test_upload_with_folder_move_fail(self, mock_delete, mock_put,
                                          mock_upload):
        mock_upload.return_value = {'id': '102',  # re-use to avoid mocks
                                    'properties': {
                                        'name': 'foo.gpx',
                                    }}
        mock_put.return_value = None
        out = self._run('upload --existing-folder folder1 foo.gpx',
                        expect_fail=True)
        self.assertIn('Failed to move', out)
        mock_delete.assert_not_called()

    @mock.patch('builtins.open')
    def test_export(self, mock_open):
        out = self._run('waypoint export wpt1 foo.gpx')
        self.assertIn('Wrote \'foo.gpx\'', out)
        mock_open.assert_called_once_with('foo.gpx', 'wb')
        fake_file = mock_open.return_value.__enter__.return_value
        fake_file.write.assert_called_once_with('object 001 format gpx')

        out = self._run('folder export folder1 foo.gpx')
        self.assertIn('Wrote \'foo.gpx\'', out)

        out = self._run('track export trk1 foo.gpx')
        self.assertIn('Wrote \'foo.gpx\'', out)

        out = self._run('folder export folder1 --format kml foo.kml')
        self.assertIn('Wrote \'foo.kml\'', out)

        out = self._run('folder export folder1 --format jpg foo',
                        expect_fail=True)

    def test_query_hidden(self):
        self._run('query foo',
                  expect_fail=True)

    @mock.patch.dict(os.environ, GAIAGPSCLIENTDEV='y')
    @mock.patch.object(FakeClient, 's')
    def test_query(self, mock_s):
        mock_r = mock.MagicMock()
        mock_r.headers = {'Content-Type': 'foo json foo'}
        mock_r.status_code = 200
        mock_r.reason = 'OK'
        mock_r.json.return_value = {'object': 'data'}
        mock_s.get.return_value = mock_r
        out = self._run('query api/objects/waypoint')
        self.assertIn('200 OK', out)
        self.assertIn('json', out)
        self.assertIn('object', out)
        mock_s.get.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint'),
            params={})
        mock_r.json.assert_called_once_with()

    @mock.patch.dict(os.environ, GAIAGPSCLIENTDEV='y')
    @mock.patch.object(FakeClient, 's')
    def test_query_args_method_quiet(self, mock_s):
        mock_r = mock.MagicMock()
        mock_r.headers = {'Content-Type': 'html'}
        mock_r.status_code = 200
        mock_r.reason = 'OK'
        mock_r.content = 'foo'
        mock_s.put.return_value = mock_r

        out = self._run('query api/objects/waypoint -X PUT -a foo=bar -q')
        self.assertNotIn('200 OK', out)
        self.assertNotIn('Content-Type', out)
        self.assertIn('foo', out)
        mock_s.put.assert_called_once_with(
            apiclient.gurl('api', 'objects', 'waypoint'),
            params={'foo': 'bar'})

    def test_url(self):
        out = self._run('waypoint url wpt1')
        self.assertEqual('https://www.gaiagps.com/datasummary/waypoint/001',
                         out.strip())

    def test_dump(self):
        out = self._run('waypoint dump wpt1')
        self.assertEqual(
            pprint.pformat(
                FakeClient().get_object('waypoint', 'wpt1')),
            out.strip())

    @mock.patch.object(FakeClient, 'test_auth')
    def test_test(self, mock_test):
        mock_test.return_value = True
        out = self._run('test')
        self.assertEqual('Success!', out.strip())

        mock_test.return_value = False
        out = self._run('test',
                        expect_fail=True)
        self.assertEqual('Unable to access gaia', out.strip())

    @mock.patch.object(FakeClient, 'test_auth')
    def test_with_debug(self, mock_test):
        mock_test.return_value = True
        self._run('--debug test')

    @mock.patch.object(FakeClient, '__init__')
    def test_client_init_login_failure(self, mock_init):
        mock_init.side_effect = Exception()
        out = self._run('test',
                        expect_fail=True)
        self.assertIn('Unable to access Gaia', out)

    @mock.patch('getpass.getpass')
    @mock.patch('os.isatty')
    @mock.patch.object(FakeClient, '__init__')
    @mock.patch.object(FakeClient, 'test_auth')
    def test_get_pass(self, mock_test, mock_client, mock_tty, mock_getpass):
        mock_tty.return_value = True
        mock_getpass.return_value = mock.sentinel.password
        mock_client.return_value = None
        self._run('--user foo@bar.com test')
        mock_getpass.assert_called_once_with()
        mock_client.assert_called_once_with('foo@bar.com',
                                            mock.sentinel.password,
                                            cookies=None)

    def test_show_waypoint(self):
        out = self._run('waypoint show wpt3')
        self.assertIn('time_created', out)
        self.assertIn('title', out)

    def test_show_folder(self):
        out = self._run('folder show folder1')
        self.assertRegex(out, r'name.*folder1')
        self.assertRegex(out, r'\| +waypoints.*\(1 items\) +\|')
        self.assertRegex(out, r'\| +tracks.*\(0 items\) +\|')
        self.assertNotIn('[ ', out)

        out = self._run('folder show --only-key name folder1')
        self.assertRegex(out, r'name.*folder1')
        self.assertNotIn('waypoints', out)
        self.assertNotIn('tracks', out)

        out = self._run('folder show --only-key name --only-key tracks '
                        'folder1')
        self.assertRegex(out, r'name.*folder1')
        self.assertRegex(out, r'\| +tracks.*\(0 items\) +\|')
        self.assertNotIn('waypoints', out)

        out = self._run('folder show -f = folder1')
        self.assertIn('name=folder1', out)
        self.assertIn('waypoints=[{', out)
        self.assertIn('tracks=[]', out)

        out = self._run('folder show --expand-key waypoints folder1')
        self.assertIn('name', out)
        self.assertRegex(out, r'\| +waypoints +\| \[{')
        self.assertNotRegex(out, r'\| +tracks +\| \[\]')

        out = self._run('folder show --expand-key waypoints '
                        '--expand-key tracks folder1')
        self.assertIn('name', out)
        self.assertRegex(out, r'\| +waypoints +\| \[{')
        self.assertRegex(out, r'\| +tracks +\| \[\]')

        out = self._run('folder show --expand-key all folder1')
        self.assertIn('name', out)
        self.assertRegex(out, r'\| +waypoints +\| \[{')
        self.assertRegex(out, r'\| +tracks +\| \[\]')

        out = self._run('folder show --only-vals folder1')
        self.assertNotIn('name', out)
        self.assertIn('folder1', out)

        out = self._run('folder show --only-key foo folder1',
                        expect_fail=True)

        out = self._run('folder show -f = --only-vals folder1',
                        expect_fail=True)
