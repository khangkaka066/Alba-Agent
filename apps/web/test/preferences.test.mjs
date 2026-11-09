import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_PREFERENCES,resolvePreferences,loadPreferences,savePreferences,shouldProceed,rememberBrowserUrl} from '../src/lib/preferences.mjs';
import {resolveBindings,actionFor,saveBindings,loadBindings} from '../src/lib/shortcuts.mjs';
const store=()=>{const values=new Map();return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)}};
test('preferences survive reload and invalid saved data cannot inject CSS or invalid modes',()=>{
 const storage=store();savePreferences(storage,{...DEFAULT_PREFERENCES,theme:'light',messageDelivery:'immediate',volume:.4});assert.equal(loadPreferences(storage).theme,'light');assert.equal(loadPreferences(storage).volume,.4);
 const unsafe=resolvePreferences({background:'url(https://tracker.test)',theme:'invalid',volume:Infinity,notifications:'false'});assert.deepEqual(unsafe,DEFAULT_PREFERENCES);
 assert.equal(resolvePreferences({volume:2}).volume,1);storage.setItem('nexus_preferences','broken');assert.deepEqual(loadPreferences(storage),DEFAULT_PREFERENCES);
});
test('automatic plan execution still respects an explicit request to wait for review',()=>{
 assert.equal(shouldProceed('always','Build a small counter'),true);assert.equal(shouldProceed('ask','Build a small counter'),false);
 for(const prompt of ['Do not execute until I review it','Wait for approval','Chờ tôi duyệt kế hoạch','Không được chạy ngay','Dừng thực thi'])assert.equal(shouldProceed('always',prompt),false,prompt);
});
test('browser history rejects credentials and executable schemes, deduplicates and caps entries',()=>{
 const storage=store();rememberBrowserUrl(storage,'javascript:alert(1)');rememberBrowserUrl(storage,'https://secret:password@example.com');assert.equal(storage.getItem('nexus_browser_history'),null);
 for(let i=0;i<102;i++)rememberBrowserUrl(storage,`https://example.com/${i}`);rememberBrowserUrl(storage,'https://example.com/101');const history=JSON.parse(storage.getItem('nexus_browser_history'));assert.equal(history.length,100);assert.equal(new Set(history).size,100);assert.equal(history[0],'https://example.com/101');
});
test('removing a keyboard binding survives reload without stealing another shortcut',()=>{
 const bindings=resolveBindings({palette:''});const storage=store();saveBindings(storage,bindings);assert.equal(loadBindings(storage).palette,'');assert.equal(actionFor(bindings,{key:'P',metaKey:true,ctrlKey:false,shiftKey:true,altKey:false}),null);
});
