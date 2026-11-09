export type Preferences = {theme:'dark'|'light'|'system';steps:'default'|'verbose';contrast:'default'|'strong';font:'system'|'sans'|'serif'|'mono';background:string;foreground:string;accent:string;conversationWidth:'narrow'|'normal'|'wide';planReview:'ask'|'always';messageDelivery:'queue'|'immediate';linkTarget:'builtin'|'external';notifications:boolean;sounds:boolean;volume:number};
export const PREFERENCES_KEY:string;
export const DEFAULT_PREFERENCES:Readonly<Preferences>;
export function resolvePreferences(value:unknown):Preferences;
export function loadPreferences(storage:Pick<Storage,'getItem'>):Preferences;
export function savePreferences(storage:Pick<Storage,'setItem'>,value:Preferences):void;
export function shouldProceed(policy:Preferences['planReview'],prompt:string):boolean;
export function rememberBrowserUrl(storage:Pick<Storage,'getItem'|'setItem'>,url:string):void;
