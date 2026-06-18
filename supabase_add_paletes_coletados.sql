-- Adiciona a coluna PC (paletes coletados) sem alterar PALETES (paletes agendados).
alter table public.deliveries
add column if not exists paletes_coletados numeric;

comment on column public.deliveries.paletes is 'Paletes agendados';
comment on column public.deliveries.paletes_coletados is 'PC - paletes coletados';
