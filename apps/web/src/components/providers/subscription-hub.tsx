"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { useLocale } from "@/components/locale-provider";
import { useModels } from "@/components/model-context";
import { apiRequest, readError } from "@/lib/api";
import { getDesktop } from "@/lib/desktop";

export type PlanCredential = { id: string; preset_id: string; status: string; base_url: string | null; is_default: boolean; available_models: string[]; settings: Record<string, string>; safe_error: string | null };
type Account = {id:string;name:string;provider:string;preset:string;installed:boolean;url:string};
const ENDPOINT = "/api/v1/settings/subscriptions/accounts";

/** Sign-in stays in the provider's official application; Nexus stores only its own revocable connection. */
export function SubscriptionHub({token,credentials,onChanged,hideHeading=false}:{token:string;credentials:PlanCredential[];onChanged:()=>Promise<void>;hideHeading?:boolean}) {
  const {t}=useLocale();
  const models=useModels();
  const [accounts,setAccounts]=useState<Account[]>([]);
  const [local,setLocal]=useState(false);
  const [desktop,setDesktop]=useState(false);
  const [loginFlow,setLoginFlow]=useState<{provider:string;id:string}|null>(null);
  const verifier=useRef<(account:Account)=>Promise<void>>(async()=>undefined);
  const [pending,setPending]=useState<string|null>(null);
  const [busy,setBusy]=useState<string|null>(null);
  const [problem,setProblem]=useState<{provider:string;text:string}|null>(null);
  const [success,setSuccess]=useState<string|null>(null);
  const reload=useCallback(async()=>{
    if(!token)return;
    const result=await apiRequest<{local:boolean;providers:Account[]}>(ENDPOINT,token);
    setLocal(result.local);setAccounts(result.providers);
  },[token]);
  useEffect(()=>{setDesktop(!!getDesktop()?.signInAccount);void reload().catch(error=>setProblem({provider:"",text:readError(error)}));},[reload]);
  useEffect(()=>{const refresh=()=>void reload().catch(()=>undefined);window.addEventListener("focus",refresh);return()=>window.removeEventListener("focus",refresh);},[reload]);
  const begin=async(account:Account)=>{
    const bridge=getDesktop();if(!bridge?.signInAccount)return;
    setBusy(account.id);setProblem(null);setSuccess(null);
    try{
      const flow=await apiRequest<{flow_id:string}>(`${ENDPOINT}/${account.id}/login`,token,{method:"POST"});
      setLoginFlow({provider:account.id,id:flow.flow_id});
      setPending(account.id);
    }catch(error){setProblem({provider:account.id,text:readError(error)})}finally{setBusy(null)}
  };
  const verify=async(account:Account)=>{
    setBusy(account.id);setProblem(null);setSuccess(null);
    try{
      const saved=await apiRequest<PlanCredential & {provider:string}>(`${ENDPOINT}/${account.id}/connect`,token,{method:"POST"});
      await onChanged();await models.refresh();
      if(saved.status.toLowerCase()==="limited"){setPending(null);setProblem({provider:account.id,text:t("accounts.limitedDescription")});return}
      if(saved.available_models[0])models.choose(`${saved.provider}/${saved.available_models[0]}`);
      setSuccess(account.id);setPending(null);window.dispatchEvent(new Event("nexus:ai-changed"));
    }catch(error){setPending(null);setProblem({provider:account.id,text:readError(error)})}finally{setBusy(null)}
  };
  verifier.current=verify;
  useEffect(()=>{
    if(!loginFlow||!token)return;
    let stopped=false;let timer:ReturnType<typeof setTimeout>|null=null;
    const poll=async()=>{
      try{
        const result=await apiRequest<{status:string}>(`${ENDPOINT}/${loginFlow.provider}/login/${loginFlow.id}`,token);
        if(stopped)return;
        if(result.status==="authorized"){
          setLoginFlow(null);
          const account=accounts.find(item=>item.id===loginFlow.provider);
          if(account)await verifier.current(account);
          return;
        }
        if(result.status!=="pending"){
          setLoginFlow(null);setPending(null);setProblem({provider:loginFlow.provider,text:t("accounts.loginFailed")});return;
        }
      }catch{if(!stopped){setLoginFlow(null);setPending(null);setProblem({provider:loginFlow.provider,text:t("accounts.loginFailed")})}return}
      if(!stopped)timer=setTimeout(()=>void poll(),1500);
    };
    timer=setTimeout(()=>void poll(),800);
    return()=>{stopped=true;if(timer)clearTimeout(timer)};
  },[loginFlow,token,accounts,t]);
  const cancel=async()=>{
    if(!loginFlow)return;
    try{await apiRequest(`${ENDPOINT}/${loginFlow.provider}/login/${loginFlow.id}/cancel`,token,{method:"POST"});setLoginFlow(null);setPending(null)}catch(error){setProblem({provider:loginFlow.provider,text:readError(error)})}
  };
  const disconnect=async(account:Account)=>{
    setBusy(account.id);setProblem(null);setSuccess(null);
    try{await apiRequest(`${ENDPOINT}/${account.id}`,token,{method:"DELETE"});await onChanged();await models.refresh();window.dispatchEvent(new Event("nexus:ai-changed"));}catch(error){setProblem({provider:account.id,text:readError(error)})}finally{setBusy(null)}
  };
  return <section className="subscription-hub nx-account-hub">
    {!hideHeading&&<h2>{t("accounts.title")}</h2>}
    {!hideHeading&&<p className="nx-account-intro">{t("accounts.description")}</p>}
    {(!local||!desktop)&&<p className="provider-alert" role="status">{t("accounts.desktopOnly")}</p>}
    {problem?.provider===""&&<p className="provider-alert provider-alert--error" role="alert">{problem.text}</p>}
    <div className="provider-grid plan-grid">{accounts.map(account=>{
      const saved=credentials.find(item=>item.settings.auth_kind==="official_cli"&&item.settings.account_provider===account.id&&["connected","limited"].includes(item.status.toLowerCase()));
      const limited=saved?.status.toLowerCase()==="limited";
      const waiting=pending===account.id;
      return <article className="provider-card plan-card nx-account-card" key={account.id} data-connector={account.id}>
        <header className="provider-card-top"><h3>{account.name}</h3><span className={`provider-status provider-status--${saved&&!limited?"connected":"unconfigured"}`}>{t(limited?"accounts.limited":saved?"accounts.connected":"accounts.notConnected")}</span></header>
        {limited&&problem?.provider!==account.id&&<p className="provider-alert" role="status">{t("accounts.limitedDescription")}</p>}
        <p>{t(`accounts.detail.${account.id}`)}</p>
        <p className="nx-account-availability">{t(account.installed?"accounts.ready":"accounts.installNeeded")}</p>
        {waiting&&<div className="nx-account-waiting" role="status"><strong>{t("accounts.waiting")}</strong><p>{t(loginFlow?"accounts.browserInstructions":"accounts.finishInstructions")}</p>{loginFlow&&<button type="button" className="button button-quiet" onClick={()=>void cancel()}>{t("accounts.cancelLogin")}</button>}</div>}
        {problem?.provider===account.id&&<p className="provider-alert provider-alert--error" role="alert">{problem.text}</p>}
        {success===account.id&&<p className="plan-result plan-result--ok" role="status">{t("accounts.verified")}</p>}
        <div className="plan-actions">
          {account.installed?<button type="button" className="button button-primary" disabled={!token||!local||!desktop||busy!==null||pending!==null} onClick={()=>void begin(account)}>{busy===account.id?t("accounts.working"):t(saved?"accounts.signInAgain":`accounts.login.${account.id}`)}</button>:<button type="button" className="button button-primary" disabled={!desktop||busy!==null||pending!==null} onClick={()=>void getDesktop()?.installAccountApp(account.id).catch(error=>setProblem({provider:account.id,text:readError(error)}))}>{t("accounts.install")}</button>}
          {account.installed&&<button type="button" className="button button-quiet" disabled={!token||!local||busy!==null} onClick={()=>void verify(account)}>{t(waiting?"accounts.finish":"accounts.check")}</button>}
          {saved&&<button type="button" className="button button-quiet" disabled={busy!==null} onClick={()=>void disconnect(account)}>{t("accounts.disconnect")}</button>}
        </div>
        {saved&&<small className="nx-account-session-note">{t("accounts.sessionNote")}</small>}
      </article>;
    })}</div>
    {!accounts.length&&!problem&&<p role="status">{t("accounts.loading")}</p>}
  </section>;
}
