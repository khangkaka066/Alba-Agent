"use client";
import {Component,type ReactNode} from 'react';
import {useLocale} from '@/components/locale-provider';
class Boundary extends Component<{children:ReactNode;title:string;body:string;retry:string},{failed:boolean}> {
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true}}
 render(){return this.state.failed?<main className="nx-interface-recovery"><h1>{this.props.title}</h1><p>{this.props.body}</p><button type="button" onClick={()=>window.location.assign('/studio')}>{this.props.retry}</button></main>:this.props.children}
}
export function InterfaceBoundary({children}:{children:ReactNode}){const {t}=useLocale();return <Boundary title={t('settings.recovery.title')} body={t('settings.recovery.body')} retry={t('settings.recovery.retry')}>{children}</Boundary>}
