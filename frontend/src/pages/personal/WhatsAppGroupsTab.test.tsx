import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WhatsAppGroupsTab } from './WhatsAppGroupsTab';
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(key:string)=>key,i18n:{language:'pt-BR'}})}));
let failed=false;
vi.mock('@/hooks/usePersonalGroups',()=>({
 usePersonalGroups:()=>({data:failed?undefined:[{id:'real-group-uuid',name:'Grupo fictício',whatsapp_id:'120363000000000123@g.us',pending_suggestions:2,accepted_suggestions:1,last_seen_at:'2026-10-27T10:00:00Z',created_at:'2026-10-27T10:00:00Z',created_by:'maia',monitored:true}],isPending:false,isError:failed,refetch:vi.fn()}),
 useSyncPersonalGroups:()=>({mutate:vi.fn(),isPending:false,isError:false})
}));
vi.mock('@/hooks/usePersonalContacts',()=>({usePersonalSuggestions:()=>({data:{pages:[[]]},isPending:false,isError:false})}));
vi.mock('./SuggestionsTab',()=>({SuggestionCard:()=>null}));
describe('registered WhatsApp groups',()=>{
 it('shows monitored registry and selects its capture history',()=>{
  failed=false;render(<WhatsAppGroupsTab/>);
  expect(screen.getByText('Grupo fictício')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/Grupo fictício/}));
  expect(screen.getByText('groups.noCaptures')).toBeInTheDocument();
 });
 it('does not confuse source errors with an empty registry',()=>{
  failed=true;render(<WhatsAppGroupsTab/>);
  expect(screen.getByText('groups.loadError')).toBeInTheDocument();
  expect(screen.queryByText('groups.empty')).not.toBeInTheDocument();
 });
});
