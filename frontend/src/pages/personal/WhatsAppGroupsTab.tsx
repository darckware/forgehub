import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, RotateCw, Search, UsersRound } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { usePersonalGroups, useSyncPersonalGroups, type PersonalWhatsAppGroup } from '@/hooks/usePersonalGroups';
import { usePersonalSuggestions } from '@/hooks/usePersonalContacts';
import { SuggestionCard } from './SuggestionsTab';
import { cn } from '@/lib/utils';

function GroupCaptures({group}:{group:PersonalWhatsAppGroup}) {
 const {t}=useTranslation('personal');
 const captures=usePersonalSuggestions('all',group.id);
 const records=captures.data?.pages.flat()??[];
 return <div className="space-y-3">
  {captures.isPending&&<p className="text-muted-foreground">{t('groups.loading')}</p>}
  {captures.isError&&<p className="text-destructive dark:text-red-400">{t('groups.captureError')}</p>}
  {!captures.isPending&&!captures.isError&&records.length===0&&<p className="text-muted-foreground">{t('groups.noCaptures')}</p>}
  {records.map(s=><SuggestionCard key={s.id} suggestion={s}/>)}
  {captures.hasNextPage&&<Button variant="outline" disabled={captures.isFetchingNextPage} onClick={()=>void captures.fetchNextPage()}>{t('groups.more')}</Button>}
 </div>;
}

export function WhatsAppGroupsTab() {
 const {t,i18n}=useTranslation('personal');
 const groups=usePersonalGroups(); const sync=useSyncPersonalGroups();
 const [search,setSearch]=useState('');const [selected,setSelected]=useState<string|null>(null);
 const visible=(groups.data??[]).filter(g=>g.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
 const current=(groups.data??[]).find(g=>g.id===selected);
 const date=(v:string|null)=>v?new Date(v).toLocaleString(i18n.language):'—';
 return <div className="space-y-4 pt-4">
  <div className="flex flex-wrap items-center justify-between gap-3">
   <p className="max-w-2xl text-sm text-muted-foreground">{t('groups.description')}</p>
   <Button variant="outline" disabled={sync.isPending} onClick={()=>sync.mutate()}><RotateCw className={cn('mr-2 h-4 w-4',sync.isPending&&'animate-spin')}/>{t('groups.sync')}</Button>
  </div>
  {sync.isError&&<p role="alert" className="text-sm text-destructive dark:text-red-400">{t('groups.syncError')}</p>}
  {groups.isError?<Card><CardContent className="space-y-3 p-4"><p role="alert" className="text-sm text-destructive dark:text-red-400">{t('groups.loadError')}</p><Button variant="outline" onClick={()=>void groups.refetch()}>{t('groups.retry')}</Button></CardContent></Card>:<>
   {groups.isPending?<Loader2 className="mx-auto h-5 w-5 animate-spin"/>:<div className="grid min-w-0 grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
    <Card><CardContent className="space-y-3 p-4">
     <div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground"/><Input className="pl-9" aria-label={t('groups.search')} placeholder={t('groups.search')} value={search} onChange={e=>setSearch(e.target.value)}/></div>
     {visible.length===0&&<p className="py-3 text-sm text-muted-foreground">{t(search?'groups.noResults':'groups.empty')}</p>}
     <div className="space-y-2">{visible.map(g=><button key={g.id} type="button" onClick={()=>setSelected(g.id)} className={cn('w-full rounded-md border p-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring',g.id===selected&&'border-primary bg-muted/50')}>
      <span className="flex items-start gap-2"><UsersRound className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"/><span className="min-w-0"><span className="block break-words font-medium">{g.name}</span><span className="mt-1 block text-xs text-muted-foreground">{t('groups.pending',{count:g.pending_suggestions})} · {t('groups.accepted',{count:g.accepted_suggestions})}</span></span></span>
     </button>)}</div>
    </CardContent></Card>
    <Card><CardContent className="space-y-4 p-4">
     {current?<><div className="space-y-2"><div className="flex flex-wrap items-start justify-between gap-2"><h2 className="break-words text-lg font-semibold">{current.name}</h2><Badge variant="secondary">{t('groups.monitored')}</Badge></div><p className="break-all font-mono text-xs text-muted-foreground">{current.whatsapp_id}</p><p className="text-xs text-muted-foreground">{t('groups.lastSeen')}: {date(current.last_seen_at)}</p></div><GroupCaptures key={current.id} group={current}/></>:<p className="py-8 text-center text-sm text-muted-foreground">{t('groups.select')}</p>}
    </CardContent></Card>
   </div>}
  </>}
 </div>;
}
