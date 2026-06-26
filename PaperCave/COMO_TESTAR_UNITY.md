# Como Testar um Paper no Unity — Paper Cave

## Visão geral do fluxo

```
PDF + FIG_*.png
     │
     ▼
 Python pipeline  (main.py run)
     │
     ▼
 outputs/{paper_id}/07_reviewer_output.json   ← resultado bruto
     │
     ▼ (unity_export.py — roda automaticamente no fim do pipeline)
     ▼
 Assets/PaperCaveData/{paper_id}/
   ├── manifest.json    ← o que o Unity lê
   └── images/
       └── FIG_1.png    ← figuras referenciadas
     │
     ▼
 Unity Editor: Tools > PaperCave > Build Cards From Manifest...
     │  (PaperCaveManifestLoader.cs lê o manifest e chama
     │   PaperCaveSceneBuilder3D.BuildCardFromData() para cada unit)
     ▼
 Cena: cartas 3D interativas dispostas em arco
```

---

## Como buildar as cartas no Unity

1. Abra o projeto Unity (`D:\3DCG\Projeto CG\pos-cg-d297`)
2. No menu: **Tools > PaperCave > Build Cards From Manifest...**
3. Na janela de arquivo que abrir, navegue até:
   `Assets/PaperCaveData/{paper_id}/manifest.json`
4. Selecione o arquivo e confirme
5. O editor vai buildar a cena `Assets/Scenes/PaperCave_Cards_3D.unity`
6. Uma popup confirma quantas units foram criadas
7. Entre em Play Mode para testar a interação

**Atalho para re-buildar:** se a cena já existe, basta rodar o menu novamente —
ele sobrescreve os GameObjects existentes.

---

## O que testar e o que checar

### Vista colapsada (card fechado)
- [ ] Badge de categoria com cor correta (ex: contribution = âmbar dourado)
- [ ] Título legível (máx 30 chars — aparece truncado se maior)
- [ ] Summary visível (máx 80 chars) — **atenção: itens de stack achatado têm summary vazio**

### Expansão (clique na carta)
- [ ] Card flutua para frente e aumenta de tamanho (1.4×)
- [ ] Conteúdo expandido aparece (descrição, figura, chart, tabela ou animação)
- [ ] Clicar novamente colapsa

### Por contentType
| contentType   | O que verificar na vista expandida |
|---------------|-------------------------------------|
| `figure`      | Imagem carregada (não branca/nula), caption e descrição |
| `chart`       | Título do chart + texto de descrição (dados completos ainda dependem da implementação do Rafael) |
| `table`       | Título + texto de descrição com os dados |
| `animation`   | Frame 1 aparece com label e descrição; botões PREV/NEXT funcionam; counter atualiza |
| `text_panel`  | Texto de descrição legível e completo |

### Posicionamento
- [ ] Unit `priority="primary"` está no centro (posição 0,0,0)
- [ ] Unidades secundárias em arco ao redor
- [ ] Luz dourada no card primário visível

### Imagens
- [ ] Carta com `contentType="figure"` mostra a imagem (não um quadrado branco)
- [ ] Se aparecer warning no Console: `could not load texture at Assets/PaperCaveData/.../images/FIG_X.png`
  → a imagem não foi copiada (ver seção abaixo)

---

## Como re-exportar as imagens manualmente

Se faltarem imagens em `Assets/PaperCaveData/{paper_id}/images/`:

```powershell
cd D:\3DCG\Projeto CG\pos-cg-d297\PaperCave
.venv\Scripts\activate
python -m utils.unity_export 1_s2_0_s1875952120301075_joyce_2020
```

Ou diretamente, especificando onde estão os FIG_*.png:

```powershell
python -m utils.unity_export 1_s2_0_s1875952120301075_joyce_2020 --paper-folder papers\1-s2.0-S1875952120301075-joyce-2020
```

---

## Como rodar um paper do zero

```powershell
cd D:\3DCG\Projeto CG\pos-cg-d297\PaperCave
.venv\Scripts\activate

# Extrai figuras (rápido, sem IA)
python main.py extract --paper papers/nome-do-paper/

# Roda o pipeline completo
python main.py run --paper papers/nome-do-paper/

# Ou retoma de um step específico
python main.py run --paper papers/nome-do-paper/ --from-step mapper
```

Outputs intermediários ficam em `outputs/{paper_id}/`:
| Arquivo | Gerado por | Conteúdo |
|---------|------------|----------|
| `01_reader_output.json` | Reader | Texto completo do PDF |
| `03_vision_insights.json` | Vision Analyst | Descrições das figuras |
| `04_summarizer_output.json` | Summarizer | Resumo denso do paper |
| `05_extractor_output.json` | Extractor | 8-10 elementos conceituais |
| `06_mapper_output.json` | Mapper | Unit Manifest (cartas + stacks) |
| `07_reviewer_output.json` | Reviewer | Manifest final com scores |

O `manifest.json` em `Assets/PaperCaveData/` é gerado a partir do `07_reviewer_output.json`
com stacks "achatados" em cards individuais.

---

## Problemas conhecidos (a corrigir)

| Problema | Onde aparece | Causa |
|----------|--------------|-------|
| `paperTitle` é o abstract inteiro | Vista da cena, popup de build | LLM não respeita a semântica do campo |
| Summary vazio em cards de stack | Vista colapsada de items de stack | `flatten_for_compat.py` não herda summary |
| FIG referenciada em frames de animação não copiada | Console Unity (warning) | `unity_export._copy_figures` não percorre `frames[].assetReference` |
| `objectScores` com menos entradas que `units` | Apenas no JSON, não afeta Unity | Flattening adiciona units depois da avaliação |

---

## Arquitetura dos scripts Unity relevantes

```
Editor/
  PaperCaveManifestLoader.cs   — lê manifest.json, chama BuildCardFromData()
  PaperCaveSceneBuilder3D.cs   — constrói cada card a partir dos dados
                                  (BuildCardFromData dispatcha por contentType)

Scripts/PaperCave/
  Card3D.cs                    — estado e animação de expand/collapse por carta
  Card3DController.cs          — input global (raycast, click, drag)
  Card3DButton.cs              — botões físicos PREV/NEXT para animation cards
  AnimationFrameView3D.cs      — step-through de frames com fade/slide
```

O `PaperCaveSceneBuilder3D.Build()` (menu "Build PaperCave_Cards_3D Scene") ainda
contém cards hardcoded do paper de protótipo — **não usar para testar novos papers**.
Usar sempre o **Build Cards From Manifest...**.
