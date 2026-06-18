-- Garante que o campo PC usado pela grade, edição, atualização rápida
-- e atualização por conversa exista fisicamente na tabela deliveries.
alter table public.deliveries
    add column if not exists pc numeric;

comment on column public.deliveries.pc is 'Paletes coletados (PC).';

-- Atualiza o cache de schema do PostgREST/Supabase após a migração.
notify pgrst, 'reload schema';
