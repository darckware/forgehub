import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
export interface PersonalWhatsAppGroup {
 id:string; whatsapp_id:string; name:string; last_seen_at:string|null; created_by:string; created_at:string;
 monitored:boolean; pending_suggestions:number; accepted_suggestions:number;
}
export function usePersonalGroups() {
 return useQuery<PersonalWhatsAppGroup[]>({queryKey:['personal','groups'],queryFn:()=>apiClient.get('/api/v1/personal/groups'),retry:false,refetchInterval:()=>document.visibilityState==='visible'?30_000:false});
}
export function useSyncPersonalGroups() {
 const client=useQueryClient();
 return useMutation({mutationFn:()=>apiClient.post<PersonalWhatsAppGroup[]>('/api/v1/personal/groups:sync',{}),onSuccess:()=>client.invalidateQueries({queryKey:['personal']})});
}
