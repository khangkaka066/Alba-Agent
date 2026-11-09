import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeSidebar, sidebarItems, conversationTime, readConversations, isUnread, sortSidebarProjects, moveSidebarProject, loadSidebar, saveSidebar } from '../src/lib/sidebar-view.mjs';
const task = (id, name, status, created, updated = created) => ({ name, run: { id, conversation_id: `thread-${id}`, status, created_at: `2026-11-0${created}T00:00:00Z`, updated_at: `2026-11-0${updated}T00:00:00Z` } });
const items = [task('a', 'Zulu', 'completed', 1, 8), task('b', 'Beta', 'running', 3, 4), task('c', 'Alpha', 'paused', 2, 5), task('d', 'Delta', 'chat', 4, 6)];
const ids = (rows) => rows.map(row => row.run.id);
const state = (value = {}) => normalizeSidebar(value);

test('creation and last update are distinct; sorting never mutates the source list', () => {
  assert.deepEqual(ids(sidebarItems(items, state())), ['a', 'd', 'c', 'b']);
  assert.deepEqual(ids(sidebarItems(items, state({ conversationSort: 'created' }))), ['d', 'b', 'c', 'a']);
  assert.deepEqual(ids(sidebarItems(items, state({ conversationSort: 'name' }))), ['c', 'b', 'd', 'a']);
  assert.deepEqual(ids(items), ['a', 'b', 'c', 'd']);
  assert.equal(conversationTime({ run: { created_at: 'invalid', finished_at: '2026-11-09T00:00:00Z' } }), Date.parse('2026-11-09T00:00:00Z'));
});
test('manual pins and active auto pins precede the chosen sort', () => {
  assert.deepEqual(ids(sidebarItems(items, state({ autoPin: true }))), ['c', 'b', 'a', 'd']);
  assert.deepEqual(ids(sidebarItems(items, state({ pinned: { 'thread-d': true } }))), ['d', 'a', 'c', 'b']);
});
test('archive hides the entire thread and can be restored without changing the input data', () => {
  const archived = state({ archived: { 'thread-a': true } });
  assert.deepEqual(ids(sidebarItems(items, archived)), ['d', 'c', 'b']);
  assert.deepEqual(ids(sidebarItems(items, { ...archived, archivedOnly: true })), ['a']);
  assert.deepEqual(ids(sidebarItems(items, { ...archived, archived: {} })), ['a', 'd', 'c', 'b']);
});
test('status and text filters compose, including empty results', () => {
  assert.deepEqual(ids(sidebarItems(items, state({ filter: 'active' }))), ['b']);
  assert.deepEqual(ids(sidebarItems(items, state({ filter: 'attention' }))), ['c']);
  assert.deepEqual(ids(sidebarItems(items, state({ filter: 'completed', query: ' DEL ' }))), ['d']);
  assert.deepEqual(sidebarItems(items, state({ query: 'no match' })), []);
});
test('read markers use actual activity; new updates and newly discovered threads become unread', () => {
  assert.equal(isUnread(items[0], state()), false);
  const baseline = readConversations(state(), items);
  assert.equal(sidebarItems(items, { ...baseline, filter: 'unread' }).length, 0);
  const updated = task('b', 'Beta', 'completed', 3, 9);
  assert.equal(isUnread(updated, baseline), true);
  assert.equal(isUnread(task('e', 'New', 'chat', 8), baseline), true);
  const read = readConversations(baseline, [updated]);
  assert.equal(isUnread(updated, read), false);
  assert.equal(isUnread(updated, baseline), true);
  assert.equal(isUnread(items[0], { ...baseline, seen: { ...baseline.seen, 'thread-a': 0 } }), true);
});
test('custom project ordering survives new activity; name and update sorting are independent', () => {
  const groups = [{ name: 'Zed', tasks: [items[0]] }, { name: 'Alba', tasks: [items[1]] }, { name: 'Empty', tasks: [] }];
  assert.deepEqual(sortSidebarProjects(groups, state({ projectOrder: ['Alba', 'Empty', 'Zed'] })).map(x => x.name), ['Alba', 'Empty', 'Zed']);
  assert.deepEqual(sortSidebarProjects(groups, state({ projectSort: 'updated' })).map(x => x.name), ['Zed', 'Alba', 'Empty']);
  assert.deepEqual(sortSidebarProjects(groups, state({ projectSort: 'name' })).map(x => x.name), ['Alba', 'Empty', 'Zed']);
  assert.deepEqual(moveSidebarProject(['Zed', 'Alba', 'Empty'], 'Alba', -1), ['Alba', 'Zed', 'Empty']);
  assert.deepEqual(moveSidebarProject(['Zed', 'Alba'], 'Zed', -1), ['Zed', 'Alba']);
});
test('preferences are scoped by key, validate stored fields and tolerate damaged or blocked storage', () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  saveSidebar(storage, 'account-a', state({ archivedOnly: true, projectOrder: ['Zed'] }));
  assert.equal(loadSidebar(storage, 'account-a').archivedOnly, true);
  assert.equal(loadSidebar(storage, 'account-b').archivedOnly, false);
  values.set('broken', '{');
  assert.deepEqual(loadSidebar(storage, 'broken'), state());
  const invalid = normalizeSidebar({ groupBy: 'bad', showTime: 'false', seen: { a: NaN, b: -2, c: 4 }, archived: { a: false, b: true }, projectOrder: ['x', 'x', 7] });
  assert.equal(invalid.groupBy, 'project'); assert.equal(invalid.showTime, true);
  assert.deepEqual(invalid.seen, { c: 4 }); assert.deepEqual(invalid.archived, { b: true }); assert.deepEqual(invalid.projectOrder, ['x']);
  const blocked = { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } };
  assert.deepEqual(loadSidebar(blocked, 'key'), state());
  assert.doesNotThrow(() => saveSidebar(blocked, 'key', state()));
});
