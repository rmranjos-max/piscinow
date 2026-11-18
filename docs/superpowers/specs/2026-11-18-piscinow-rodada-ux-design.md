# Piscinow — Rodada de UX e jornada única do comprador

**Data:** 2026-11-18
**Status:** aprovado pelo usuário. O protótipo navegável "Piscinow Rodada de UX" foi aprovado por inteiro ("aprovo tudo"), com dois acréscimos pedidos por ele: fotos para o comprador ver o que compra (feito antes desta rodada) e tudo responsivo no celular. Decisão sobre repasse: "Tudo para a loja".
**Referência visual:** protótipo `https://claude.ai/artifact/Lvb4jJLXcV6NpRu5tBR38z` (7 telas).

## Decisões do usuário

1. **A proposta aceita vira o projeto e define o pagamento por fases.** A jornada do comprador é uma só: Briefing → Propostas → Aceite → Pagamento por fases → Obra.
2. **Repasse:** o valor aceito vai inteiro para a loja da proposta, dividido pela equipe nas 4 fases financeiras existentes. O pagamento do instalador fica entre loja e instalador até as regras de repasse e fee serem definidas.
3. **Responsivo:** toda tela usável no celular (390 px), sem rolagem horizontal da página.

## Regras

1. **Aceite cria o projeto.** Ao aceitar, o projeto do comprador passa a apontar para a proposta aceita e fica confirmado. Se o comprador já tiver um projeto do caminho antigo **com pagamento criado**, o aceite não o altera e a equipe é avisada no histórico (caso de transição, não deve ocorrer no piloto).
2. **Cronograma a partir da proposta.** Para projeto vindo de proposta, a equipe informa quanto de cada fase; a **soma precisa ser igual ao total aceito**, e cada fase é repassada à loja. As regras de pagamento, liberação por fase e trava em produção continuam as mesmas.
3. **O caminho antigo deixa de ser oferecido**, mas continua funcionando para dados existentes: a vitrine vira só consulta ("Explorar piscinas", sem "Escolher"); Meu projeto mostra a proposta aceita.
4. **Nada definitivo com um clique:** aceitar passa por uma tela de conferência; enviar proposta passa por uma revisão "é isto que o comprador vai receber".
5. **Retorno de cada ação** (salvo, enviado, removido) aparece na própria página; erros aparecem junto do campo.
6. **Horários em Brasília** em todas as telas.

## Entrega em partes, cada uma com CI verde

- **R1** Proposta aceita → projeto e cronograma (dados, migração, regras e testes).
- **R2** Jornada única do comprador: Início em 5 etapas, menu de 5 itens, Meu projeto com a proposta, vitrine só consulta, horário de Brasília e avisos de retorno.
- **R3** Propostas e aceite: escolha entre mensagem e pedido de revisão, data das mensagens, tela de conferência.
- **R4** Consultor sem recarregar a página (melhoria progressiva: sem JavaScript continua funcionando), "digitando" e respostas rápidas.
- **R5** Loja: caixa em lista com filtros e página da oportunidade em abas, total ao vivo e revisão antes de enviar.
- **R6** Admin: oportunidade em abas na ordem do trabalho, ações destrutivas em "Mais ações".
- **R7** Responsivo: tabelas viram cartões no celular; revisão de todas as telas a 390 px; capturas e relatório.

## Fora desta rodada

Contadores de novidades no menu e notificações (dependem de e-mail), landing e telas de login no visual novo, repasse ao instalador, fee.
