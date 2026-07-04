
        let currentRegenPaper = null;
        let currentRegenStep = null;
        
        function openRegenModal(paperId, step) {
            currentRegenPaper = paperId;
            currentRegenStep = step;
            document.getElementById('regen-step-name').textContent = step;
            document.getElementById('regen-prompt').value = '';
            document.getElementById('regen-error-msg').style.display = 'none';
            document.getElementById('regen-modal').style.display = 'flex';
        }
        
        function submitRegen() {
            const prompt = document.getElementById('regen-prompt').value.trim();
            if (!prompt) return alert('Por favor digite uma instrução para o Agente Corretor.');
            
            const btn = document.getElementById('regen-submit-btn');
            const errorMsg = document.getElementById('regen-error-msg');
            
            const editedJsonStr = document.getElementById(`json-${currentRegenStep}`).value;
            
            btn.disabled = true;
            btn.textContent = 'Aguarde. Agente rodando...';
            errorMsg.style.display = 'none';
            
            fetch(`/api/paper/${currentRegenPaper}/correct_step`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    step_id: currentRegenStep,
                    prompt: prompt,
                    edited_json: editedJsonStr
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('regen-modal').style.display = 'none';
                    // Reload UI
                    viewPaperDetail(currentRegenPaper);
                } else {
                    errorMsg.textContent = 'Erro: ' + (data.error || 'Falha desconhecida');
                    errorMsg.style.display = 'block';
                }
            })
            .catch(err => {
                errorMsg.textContent = 'Erro de rede: ' + err;
                errorMsg.style.display = 'block';
            })
            .finally(() => {
                btn.disabled = false;
                btn.textContent = '🚀 Executar Agente';
            });
        }
        
        function continuePipelineFrom(paperId, step) {
            const editedJsonStr = document.getElementById(`json-${step}`).value;
            // 1. Send the edited JSON to an API to save it first...
            // Wait, I can actually start the pipeline via run_pipeline, but I need to save the JSON first.
            // Let's create a quick save_json route... Wait, we can just use the pipeline API and tell it to resume.
            // But we need to save the file.
            fetch(`/api/paper/${paperId}/save_json_raw`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ step: step, content: editedJsonStr })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(`JSON salvo. A pipeline será iniciada a partir do passo seguinte.`);
                    // Now start pipeline!
                    // What is the next step?
                    let nextStepMapping = {
                        "01_reader_output": "vision_analyst",
                        "02_vision_analyst_output": "summarizer",
                        "03_summarizer_output": "extractor",
                        "04_extractor_output": "mapper",
                        "05_mapper_output": "reviewer",
                        "07_reviewer_output": "none" // End
                    };
                    let resumeStep = nextStepMapping[step];
                    
                    if (resumeStep === "none") {
                        alert("Pipeline já finalizada neste ponto. (Reviewer)");
                        return;
                    }
                    
                    if (!resumeStep) {
                        resumeStep = "auto";
                    }
                    
                    // Switch to Pipeline tab
                    document.querySelector('.tab-btn').click(); 
                    
                    // Trigger run_pipeline
                    fetch("/api/run_pipeline", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            papers: [paperId],
                            simulate: document.getElementById("simulate-toggle").checked,
                            from_step: resumeStep,
                            simple_mode: document.getElementById("simple-mode-checkbox").checked
                        })
                    }).then(res => res.json()).then(resp => {
                        if (resp.success) {
                            connectEventSource();
                            document.getElementById("start-btn").style.display = "none";
                            document.getElementById("cancel-btn").style.display = "block";
                            document.getElementById("cancel-btn").disabled = false;
                        } else {
                            alert("Erro ao rodar pipeline: " + resp.error);
                        }
                    });
                } else {
                    alert('Erro ao salvar: ' + data.error);
                }
            });
        }
        
        function renderStaticManifest(paperId) {
            const board = document.getElementById('static-manifest-canvas');
            if (!board) return;
            board.innerHTML = '<div style="color: var(--text-muted); margin-top: 40px;">Carregando...</div>';
            
            fetch(`/api/unity_assets/${paperId}/manifest`)
                .then(res => res.json())
                .then(data => {
                    board.innerHTML = '';
                    const details = data.gameObjects || [];
                    if (details.length === 0) {
                        board.innerHTML = '<div style="color: var(--text-muted); margin-top: 40px; text-align: center;">Nenhuma carta/elemento no manifest.<br><small>Aguardando conclusão da fase 07</small></div>';
                        return;
                    }
                    
                    details.forEach(det => {
                        const card = document.createElement('div');
                        card.style.cssText = `
                            width: 140px; height: 180px;
                            background: rgba(255,255,255,0.03); backdrop-filter: blur(10px);
                            border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
                            padding: 8px; display: flex; flex-direction: column;
                            box-shadow: 0 5px 15px rgba(0,0,0,0.5); font-size: 10px;
                        `;
                        
                        let contentHtml = '';
                        if (det.displayType === "image" && det.imageFileName) {
                            contentHtml = `<div style="flex:1; background: url('/api/unity_assets/${paperId}/images/${det.imageFileName}') center/contain no-repeat; margin-bottom: 5px;"></div>`;
                        } else {
                            const textCts = det.textContent || (det.visualElementData ? det.visualElementData.content : "Sem texto");
                            contentHtml = `<div style="flex:1; overflow:hidden; color: #ccc; margin-bottom: 5px;">${textCts.substring(0, 100)}...</div>`;
                        }
                        
                        card.innerHTML = `
                            ${contentHtml}
                            <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 4px; color: var(--accent-cyan); font-weight: 700;">${det.type || "Element"}</div>
                            <div style="color: var(--text-muted);">${det.unitId || "No ID"}</div>
                        `;
                        board.appendChild(card);
                    });
                })
                .catch(err => {
                    board.innerHTML = `<div style="color: var(--accent-rose); margin-top: 40px;">Erro ao carregar preview: ${err}</div>`;
                });
        }
    // Global variables
    let papersData = [];
        let eventSource = null;
        let jobTimer = null;

        // On document load
        document.addEventListener("DOMContentLoaded", () => {
            loadPapers();
            loadAssetsStatus();
        });

        // Fetch discovered papers
        function loadPapers() {
            fetch("/api/papers")
                .then(res => res.json())
                .then(data => {
                    papersData = data;
                    renderPaperCheckboxes();
                    renderExplorerList();
                })
                .catch(err => console.error("Error loading papers:", err));
        }

        // Render paper grid cards in Tab 1
        function renderPaperCheckboxes() {
            const unprocessedList = document.getElementById("unprocessed-list");
            const processedList = document.getElementById("processed-list");
            
            unprocessedList.innerHTML = "";
            processedList.innerHTML = "";
            
            let unprocessedCount = 0;
            let processedCount = 0;
            
            papersData.forEach(paper => {
                const coverUrl = `/api/paper/${paper.paper_id}/page/0/render`;
                const itemHtml = `
                    <div class="paper-grid-card" onclick="toggleCheckbox('${paper.paper_id}')" style="cursor: pointer; position: relative; border-radius: 8px; overflow: hidden; border: 2px solid transparent; background: rgba(0,0,0,0.4); transition: transform 0.2s, border-color 0.2s;" id="card-${paper.paper_id}">
                        <div style="height: 160px; background-image: url('${coverUrl}'); background-size: cover; background-position: top center; border-bottom: 1px solid var(--border-color);"></div>
                        <div style="padding: 10px; display: flex; flex-direction: column; align-items: center; gap: 6px;">
                            <div style="font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; text-align: center;" title="${paper.paper_id}">${paper.paper_id}</div>
                            <div style="font-size: 11px; background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 10px; color: var(--text-light);">${paper.image_count} figs</div>
                        </div>
                        <input type="checkbox" id="check-${paper.paper_id}" value="${paper.paper_id}" style="position: absolute; top: 10px; left: 10px; width: 18px; height: 18px; pointer-events: none;" onchange="updateCardStyle('${paper.paper_id}')">
                    </div>
                `;
                
                if (paper.fully_processed) {
                    processedList.insertAdjacentHTML("beforeend", itemHtml);
                    processedCount++;
                } else {
                    unprocessedList.insertAdjacentHTML("beforeend", itemHtml);
                    unprocessedCount++;
                }
            });
            
            document.getElementById("unprocessed-count").textContent = unprocessedCount;
            document.getElementById("processed-count").textContent = processedCount;
            
            updateStartButtonState();
        }
        
        function updateCardStyle(paperId) {
            const check = document.getElementById(`check-${paperId}`);
            const card = document.getElementById(`card-${paperId}`);
            if (check && card) {
                if (check.checked) {
                    card.style.borderColor = 'var(--primary)';
                    card.style.boxShadow = '0 0 15px rgba(0, 224, 255, 0.4)';
                    card.style.transform = 'translateY(-2px)';
                } else {
                    card.style.borderColor = 'transparent';
                    card.style.boxShadow = 'none';
                    card.style.transform = 'none';
                }
            }
        }

        // Toggle checkbox helper
        function toggleCheckbox(paperId) {
            const check = document.getElementById(`check-${paperId}`);
            if (check) {
                check.checked = !check.checked;
                updateCardStyle(paperId);
                updateStartButtonState();
            }
        }

        // Select all / Deselect all
        function toggleSelectAll(select) {
            const checkboxes = document.querySelectorAll('#unprocessed-list input[type="checkbox"], #processed-list input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = select;
                const paperId = cb.value;
                updateCardStyle(paperId);
            });
            updateStartButtonState();
        }

        // Enable/Disable start button
        function updateStartButtonState() {
            const checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
            // Filter out simulate switch and simple mode checkbox
            const paperChecks = Array.from(checkboxes).filter(cb => cb.id !== "simulate-toggle" && cb.id !== "simple-mode-checkbox");
            document.getElementById("start-btn").disabled = paperChecks.length === 0;
        }

        // Render paper explorer list in Tab 2
        function renderExplorerList() {
            const explorerList = document.getElementById("explorer-list");
            explorerList.innerHTML = "";
            
            papersData.forEach(paper => {
                const statusDot = paper.fully_processed ? 
                    `<span style="color: var(--accent-emerald)">●</span>` : 
                    `<span style="color: var(--text-muted)">○</span>`;
                explorerList.insertAdjacentHTML("beforeend", `
                    <div class="explorer-list-item" id="explore-${paper.paper_id}" onclick="viewPaperDetail('${paper.paper_id}')">
                        <span>${paper.paper_id}</span>
                        ${statusDot}
                    </div>
                `);
            });
        }

        // View paper details in Tab 2
        function viewPaperDetail(paperId) {
            // Set active list item
            document.querySelectorAll(".explorer-list-item").forEach(el => el.classList.remove("active"));
            document.getElementById(`explore-${paperId}`).classList.add("active");
            
            const detailContainer = document.getElementById("explorer-detail");
            detailContainer.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted)">Carregando detalhes do paper...</div>`;
            
            fetch(`/api/paper/${paperId}`)
                .then(res => res.json())
                .then(data => {
                    if (data.error) {
                        detailContainer.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--accent-rose)">Erro da API: ${data.error}</div>`;
                        return;
                    }
                    const extracted = data.extracted || {};
                    const pageCount = data.page_count || 0;
                    
                    detailContainer.innerHTML = `
                        <div class="paper-header-card" style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.2); padding: 15px 20px; border-radius: 8px; border: 1px solid var(--border-color); margin-bottom: 20px;">
                            <div>
                                <h1 class="paper-title-big" style="margin: 0; font-size: 20px;">${paperId}</h1>
                                <p style="color: var(--text-muted); font-size: 13px; margin-top: 6px; margin-bottom: 0;">
                                    PDF original: <strong style="color: var(--text-light)">${data.pdf_name || "N/A"}</strong> | Total de páginas: <strong style="color: var(--text-light)">${pageCount}</strong>
                                </p>
                            </div>
                        </div>
                        
                        <div class="phase-editor-container" style="display: flex; gap: 20px; height: calc(100vh - 230px); min-height: 600px;">
                            <!-- Left: Canvas -->
                            <div style="flex: 1.2; background: radial-gradient(circle at center, #111 0%, #030408 100%); border: 1px solid var(--border-color); border-radius: 8px; position: relative; overflow: hidden; display: flex; flex-direction: column;">
                                <div style="padding: 10px 15px; background: rgba(0,0,0,0.5); border-bottom: 1px solid var(--border-color); font-weight: 600; font-size: 13px; display: flex; justify-content: space-between; align-items: center;">
                                    <span>🖼️ Manifest Unity Preview (Apenas Leitura)</span>
                                    <button class="btn btn-secondary btn-sm" onclick="renderStaticManifest('${paperId}')" style="padding: 4px 8px; font-size: 11px;">🔄 Atualizar Preview</button>
                                </div>
                                <div id="static-manifest-canvas" style="flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-wrap: wrap; justify-content: center; align-content: flex-start; gap: 20px;">
                                    <div style="color: var(--text-muted); margin-top: 40px;">Carregando visualização do manifest final (fase 07)...</div>
                                </div>
                            </div>
                            
                            <!-- Right: Phase Blocks -->
                            <div style="flex: 1; display: flex; flex-direction: column; gap: 15px; overflow-y: auto; padding-right: 5px;">
                                <div style="font-weight: 600; font-size: 14px; margin-bottom: 2px; color: var(--text-light); border-bottom: 1px solid var(--border-color); padding-bottom: 10px;">📝 Editor de Fases (Pipeline JSON)</div>
                                <div id="phase-blocks-container" style="display: flex; flex-direction: column; gap: 15px;">
                                </div>
                            </div>
                        </div>
                    `;
                    
                    const pipelineData = data.pipeline_data || {};
                    let blocksHtml = '';
                    const steps = Object.keys(pipelineData).sort();

                    if (steps.length === 0) {
                        blocksHtml = '<div style="color: var(--text-muted); text-align: center; margin-top: 40px; padding: 20px; border: 1px dashed var(--border-color); border-radius: 8px;">Nenhum dado de pipeline encontrado.<br><br>Execute a pipeline na aba "Pipeline Executor" primeiro.</div>';
                    } else {
                        steps.forEach(step => {
                            // Format JSON nicely if possible
                            let rawContent = pipelineData[step];
                            try {
                                rawContent = JSON.stringify(JSON.parse(rawContent), null, 4);
                            } catch(e) {}
                            
                            blocksHtml += `
                            <div class="card" style="padding: 15px; border-radius: 8px; margin: 0; background: rgba(0,0,0,0.15);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                    <h3 style="margin: 0; font-size: 14px; color: var(--accent-cyan);">${step}</h3>
                                    <div>
                                        <button class="btn btn-sm btn-secondary" onclick="document.getElementById('json-${step}').disabled = false; this.style.display='none'; document.getElementById('actions-${step}').style.display='flex';">✏️ Editar JSON</button>
                                    </div>
                                </div>
                                <textarea id="json-${step}" style="width: 100%; height: 250px; background: rgba(0,0,0,0.5); border: 1px solid var(--border-color); color: #fff; font-family: monospace; font-size: 11px; padding: 10px; border-radius: 4px; resize: vertical; line-height: 1.4;" disabled>${rawContent}</textarea>
                                
                                <div id="actions-${step}" style="display: none; justify-content: space-between; margin-top: 10px; gap: 10px;">
                                    <button class="btn btn-sm" style="background-color: var(--accent-rose); flex: 1; box-shadow: 0 0 10px rgba(244, 63, 94, 0.2);" onclick="openRegenModal('${paperId}', '${step}')">🤖 Acionar Agente Corretor p/ Fase</button>
                                    <button class="btn btn-sm" style="flex: 1;" onclick="continuePipelineFrom('${paperId}', '${step}')">⏩ Salvar Edições e Continuar Pipeline Daqui</button>
                                </div>
loadPapers();
            renderStaticManifest(paperId);
        }

        // Fetch Assets status in Tab 3
        function loadAssetsStatus() {
            const list = document.getElementById("unity-assets-list");
            list.innerHTML = `<div style="text-align: center; color: var(--text-muted);">Carregando status...</div>`;
            
            fetch("/api/unity_assets")
                .then(res => res.json())
                .then(data => {
                    list.innerHTML = "";
                    if (!data || data.length === 0) {
                        list.innerHTML = `<div style="text-align: center; color: var(--text-muted);">Nenhum projeto com assets exportados.</div>`;
                        return;
                    }
                    
                    data.forEach(folder => {
                        list.insertAdjacentHTML("beforeend", `
                            <div class="card" style="display:flex; justify-content:space-between; align-items:center;">
                                <div>
                                    <strong style="color: var(--text-light);">${folder.folder_name}</strong>
                                    <div style="color: var(--text-muted); font-size: 12px;">Images: ${folder.image_count} | Manifest: ${folder.manifest_exists ? "✅ Yes" : "❌ No"}</div>
                                </div>
                                <div>
                                    <button class="btn btn-secondary btn-sm" onclick="previewUnityLayout('${folder.folder_name}')" style="margin-right: 8px;">
                                        👁️ Preview
                                    </button>
                                    <button class="btn btn-sm" onclick="exportToUnity('${folder.folder_name}')" style="background-color: var(--primary);">
                                        🚀 Force Re-Export
                                    </button>
                                </div>
                            </div>
                        `);
                    });
                })
                .catch(err => {
                    list.innerHTML = `<div style="text-align: center; color: var(--accent-rose);">Erro: ${err}</div>`;
                });
        }
        
        // Settings Loading & Saving
        function loadSettings() {
            fetch("/api/settings")
                .then(res => res.json())
                .then(data => {
                    if (data.provider) document.getElementById('llm-provider-select').value = data.provider;
                    if (data.model) document.getElementById('llm-model-input').value = data.model;
                })
                .catch(err => console.error("Error loading settings", err));
        }
        
        function saveLlmSettings() {
            const provider = document.getElementById('llm-provider-select').value;
            const model = document.getElementById('llm-model-input').value.trim();
            
            if (!model) return alert('Por favor, informe o Model ID.');
            
            fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider: provider, model: model })
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    alert("Configurações salvas com sucesso!");
                } else {
                    alert("Erro ao salvar: " + data.error);
                }
            })
            .catch(err => alert("Erro na requisição: " + err));
        }

        // Initialize
        document.addEventListener("DOMContentLoaded", () => {
            loadPapers();
            loadAssetsStatus();
            loadSettings();
        });

        // Trigger manual Unity Export
        function exportAssetsToUnity(paperId, btnElement) {
            btnElement.disabled = true;
            btnElement.textContent = "Exportando...";
            
            fetch(`/api/export_unity/${paperId}`, { method: "POST" })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert(`Exportado com sucesso para Unity: ${paperId}`);
                        loadAssetsStatus();
                    } else {
                        alert(`Erro ao exportar: ${data.error}`);
                    }
                })
                .catch(err => alert(`Falha na requisição: ${err}`))
                .finally(() => {
                    btnElement.disabled = false;
                    btnElement.textContent = "🔄 Re-exportar";
                });
        }

        // Preview Unity Layout Modal
        function previewUnityLayout(paperId) {
            const modal = document.getElementById('unity-preview-modal');
            document.getElementById('preview-paper-id').textContent = paperId;
            const board = document.getElementById('preview-board');
            board.innerHTML = '<div style="color: #fff; text-align: center; margin-top: 20%; font-size: 20px;">Carregando Cena...</div>';
            modal.style.display = 'flex';
            
            fetch(`/api/unity_assets/${paperId}/manifest`)
                .then(res => res.json())
                .then(data => {
                    board.innerHTML = '';
                    board.style.display = 'flex';
                    board.style.flexWrap = 'wrap';
                    board.style.justifyContent = 'center';
                    board.style.alignContent = 'flex-start';
                    board.style.gap = '40px';
                    board.style.padding = '60px';
                    board.style.overflowY = 'auto';
                    
                    const details = data.gameObjects || [];
                    if (details.length === 0) {
                        board.innerHTML = '<div style="color: #fff; text-align: center; margin-top: 20%; font-size: 20px;">Nenhuma carta exportada no manifest.</div>';
                        return;
                    }
                    
                    details.forEach(det => {
                        const cardWidth = 240;
                        const cardHeight = 320;
                        const rot = Math.random() * 8 - 4;
                        
                        const card = document.createElement('div');
                        card.style.cssText = `
                            position: relative; left: 0px; top: 0px;
                            width: ${cardWidth}px; height: ${cardHeight}px;
                            background: rgba(255,255,255,0.03); backdrop-filter: blur(10px);
                            border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
                            padding: 12px; transform: rotate(${rot}deg);
                            box-shadow: 0 15px 35px rgba(0,0,0,0.6);
                            transition: transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.4s;
                            display: flex; flex-direction: column; cursor: grab; user-select: none;
                            flex-shrink: 0;
                        `;
                        
                        card.onmouseenter = () => { card.style.transform = `rotate(0deg) scale(1.15)`; card.style.zIndex = 100; card.style.boxShadow = '0 25px 50px rgba(0,224,255,0.2)'; };
                        card.onmouseleave = () => { card.style.transform = `rotate(${rot}deg) scale(1)`; card.style.zIndex = 1; card.style.boxShadow = '0 15px 35px rgba(0,0,0,0.6)'; };
                        
                        let isDragging = false;
                        let startMouseX, startMouseY, startCardX, startCardY;
                        
                        card.onmousedown = (e) => {
                            isDragging = true;
                            card.style.cursor = 'grabbing';
                            card.style.transition = 'none'; // remove transition for smooth drag
                            startMouseX = e.clientX;
                            startMouseY = e.clientY;
                            startCardX = parseFloat(card.style.left) || 0;
                            startCardY = parseFloat(card.style.top) || 0;
                        };
                        
                        window.addEventListener('mousemove', (e) => {
                            if (!isDragging) return;
                            card.style.left = `${startCardX + (e.clientX - startMouseX)}px`;
                            card.style.top = `${startCardY + (e.clientY - startMouseY)}px`;
                        });
                        
                        window.addEventListener('mouseup', () => {
                            if(isDragging) {
                                isDragging = false;
                                card.style.cursor = 'grab';
                                card.style.transition = 'transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), box-shadow 0.4s';
                            }
                        });
                        
                        let contentHtml = '';
                        if (det.displayType === 'image') {
                            contentHtml = `
                                <div style="flex: 1; display: flex; justify-content: center; align-items: center; overflow: hidden; border-radius: 8px; background: rgba(0,0,0,0.6); pointer-events: none;">
                                    <img src="/api/unity_assets/${paperId}/images/${det.relatedImage}" style="max-width: 100%; max-height: 100%; object-fit: contain;" onerror="this.outerHTML='<span style=\\'color:var(--accent-rose)\\'>Image Not Found</span>'">
                                </div>
                            `;
                        } else {
                            contentHtml = `
                                <div style="flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; overflow: hidden; border-radius: 8px; background: rgba(255,255,255,0.05); padding: 16px; pointer-events: none;">
                                    <div style="font-size: 13px; color: #fff; text-align: justify; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 10; -webkit-box-orient: vertical;">${det.visualMetaphor || det.suggestedName}</div>
                                </div>
                            `;
                        }
                        
                        card.innerHTML = `
                            ${contentHtml}
                            <div style="padding-top: 12px; text-align: center; color: var(--accent-cyan); font-family: 'Fira Code', monospace; font-size: 13px; font-weight: bold; pointer-events: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                ${det.suggestedName || 'Unnamed'}
                            </div>
                        `;
                        board.appendChild(card);
                    });
                })
                .catch(err => {
                    board.innerHTML = `<div style="color: var(--accent-rose); text-align: center; margin-top: 20%; font-size: 20px;">Erro ao carregar manifest: ${err}</div>`;
                });
        }

        function closeUnityPreview() {
            document.getElementById('unity-preview-modal').style.display = 'none';
            document.getElementById('preview-board').innerHTML = '';
        }

        // Start pipeline execution
        function startPipeline() {
            const simulate = document.getElementById("simulate-toggle").checked;
            const fromStep = document.getElementById("from-step-select").value;
            const simpleMode = document.getElementById("simple-mode-checkbox").checked;
            
            // Get selected papers
            const selectedCheckboxElements = document.querySelectorAll('#unprocessed-list input[type="checkbox"]:checked, #processed-list input[type="checkbox"]:checked');
            const paperIds = Array.from(selectedCheckboxElements).map(cb => cb.value);
            
            if (paperIds.length === 0) return;
            
            // Setup UI states
            document.getElementById("start-btn").disabled = true;
            const terminal = document.getElementById("terminal-body");
            terminal.innerHTML = `<div class="terminal-line" style="color: var(--accent-cyan)">[CONTROL] Solicitando inicialização do pipeline para ${paperIds.length} paper(s)...</div>`;
            
            // Post execution call
            fetch("/api/pipeline/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    paper_ids: paperIds,
                    simulate: simulate,
                    from_step: fromStep,
                    simple_mode: simpleMode
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    terminal.insertAdjacentHTML("beforeend", `<div class="terminal-line" style="color: var(--accent-emerald)">[CONTROL] Pipeline iniciado com sucesso. Conectando canal de logs...</div>`);
                    
                    // Toggle Buttons
                    document.getElementById("start-btn").style.display = "none";
                    document.getElementById("cancel-btn").style.display = "block";
                    document.getElementById("cancel-btn").disabled = false;
                    
                    connectEventSource();
                } else {
                    terminal.insertAdjacentHTML("beforeend", `<div class="terminal-line" style="color: var(--accent-rose)">[ERRO] Falha ao iniciar: ${data.error}</div>`);
                    document.getElementById("start-btn").disabled = false;
                }
            })
            .catch(err => {
                terminal.insertAdjacentHTML("beforeend", `<div class="terminal-line" style="color: var(--accent-rose)">[ERRO] Falha na rede: ${err}</div>`);
                document.getElementById("start-btn").disabled = false;
            });
        }

        // Cancel pipeline execution
        function cancelPipeline() {
            const cancelBtn = document.getElementById("cancel-btn");
            cancelBtn.disabled = true;
            cancelBtn.textContent = "Cancelando...";
            
            fetch("/api/pipeline/cancel", { method: "POST" })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        appendTerminalLine("\n[SISTEMA] Cancelamento enviado com sucesso.");
                    } else {
                        appendTerminalLine(`\n[ERRO] Erro ao cancelar: ${data.message || data.error}`);
                        cancelBtn.disabled = false;
                        cancelBtn.textContent = "Cancelar Processamento";
                    }
                })
                .catch(err => {
                    appendTerminalLine(`\n[ERRO] Falha ao enviar cancelamento: ${err}`);
                    cancelBtn.disabled = false;
                    cancelBtn.textContent = "Cancelar Processamento";
                });
        }

        // Polling pipeline status
        function connectEventSource() {
            if (jobTimer) clearInterval(jobTimer);
            let lastLogCount = 0;
            
            jobTimer = setInterval(() => {
                fetch("/api/pipeline/status")
                    .then(res => res.json())
                    .then(data => {
                        if (!data.active && data.total === 0) {
                            clearInterval(jobTimer);
                            return;
                        }
                        
                        // New logs
                        const newLogs = data.logs || [];
                        if (newLogs.length > lastLogCount) {
                            for (let i = lastLogCount; i < newLogs.length; i++) {
                                appendTerminalLine(newLogs[i]);
                            }
                            lastLogCount = newLogs.length;
                        }
                        
                        // Update Progress UI (simulate the event structure)
                        updateProgressUI({
                            total: data.total,
                            current: data.current_paper ? 1 : 0, // Simplified for now
                            paper_id: data.current_paper,
                            elapsed_time: data.elapsed,
                            estimated_remaining: data.estimated_remaining,
                            status: data.status_text
                        });
                        
                        // Finished checking
                        if (!data.active && data.total > 0) {
                            clearInterval(jobTimer);
                            appendTerminalLine(`\n[FINALIZADO] Lote completo finalizado!`);
                            
                            document.getElementById("start-btn").style.display = "block";
                            document.getElementById("start-btn").disabled = false;
                            document.getElementById("cancel-btn").style.display = "none";
                            
                            loadPapers();
                            loadAssetsStatus();
                        }
                    })
                    .catch(err => {
                        console.error("Polling error:", err);
                        clearInterval(jobTimer);
                    });
            }, 1000);
        }

        // Parse log lines and color-code them in terminal
        function appendTerminalLine(text) {
            const terminal = document.getElementById("terminal-body");
            let lineClass = "";
            
            // Detect lines
            if (text.startsWith("[SIMULATOR]")) lineClass = "log-sim";
            else if (text.startsWith("[PIPELINE]")) lineClass = "log-pipe";
            else if (text.startsWith("[SUCESSO]") || text.startsWith("[FINISHED]")) lineClass = "log-success";
            else if (text.includes("✗") || text.includes("FALHOU") || text.includes("error") || text.includes("ERRO") || text.includes("[FALHA]")) lineClass = "log-error";
            else if (text.includes("✓") || text.includes("concluído")) lineClass = "log-done";
            else if (text.includes("+-")) lineClass = "log-step";
            else if (text.startsWith("===") || text.startsWith("====")) lineClass = "log-header";
            
            const lineHtml = `<div class="terminal-line ${lineClass}">${escapeHtml(text)}</div>`;
            terminal.insertAdjacentHTML("beforeend", lineHtml);
            
            // Auto scroll to bottom
            terminal.scrollTop = terminal.scrollHeight;
        }

        // Update progress panel UI elements
        function updateProgressUI(data) {
            const fill = document.getElementById("progress-bar-fill");
            const statusBadge = document.getElementById("status-badge");
            const progressText = document.getElementById("progress-text");
            const elapsedVal = document.getElementById("elapsed-time");
            const remainingVal = document.getElementById("remaining-time");
            
            const pct = data.total_papers > 0 ? (data.current_index / data.total_papers) * 100 : 0;
            fill.style.width = `${pct}%`;
            
            statusBadge.className = `progress-status-badge ${data.status}`;
            statusBadge.textContent = data.status === "running" ? "Executando" : (data.status === "completed" ? "Concluído" : "Falhou");
            
            if (data.status === "running") {
                progressText.textContent = `Processando: ${data.current_paper_id} (${data.current_index + 1} de ${data.total_papers})`;
            } else {
                progressText.textContent = `Progresso Geral: ${data.current_index} de ${data.total_papers} papers`;
            }
            
            elapsedVal.textContent = formatTime(data.elapsed_time);
            remainingVal.textContent = formatTime(data.estimated_remaining);
        }

        function updateProgressFinished(data) {
            const fill = document.getElementById("progress-bar-fill");
            const statusBadge = document.getElementById("status-badge");
            const progressText = document.getElementById("progress-text");
            const remainingVal = document.getElementById("remaining-time");
            
            fill.style.width = "100%";
            statusBadge.className = "progress-status-badge completed";
            statusBadge.textContent = "Concluído";
            progressText.textContent = "Lote finalizado!";
            remainingVal.textContent = "00:00";
        }

        // Time formatter
        function formatTime(seconds) {
            if (isNaN(seconds) || seconds < 0) return "00:00";
            const m = Math.floor(seconds / 60);
            const s = Math.floor(seconds % 60);
            return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        }

        // Collapsible sections toggle
        function toggleCollapsible(header) {
            const content = header.nextElementSibling;
            const arrow = header.querySelector("span:last-child");
            if (content.style.display === "none") {
                content.style.display = "block";
                arrow.textContent = "▼";
            } else {
                content.style.display = "none";
                arrow.textContent = "▲";
            }
        }

        // Shortcut to run extraction on all papers from explorer
        function runExtractionOnAll() {
            // Switch to pipeline tab
            const firstTabBtn = document.querySelector('.tabs button:nth-child(1)');
            if (firstTabBtn) firstTabBtn.click();
            
            // Set from-step to extractor
            document.getElementById('from-step-select').value = 'extractor';
            
            // Uncheck simulate
            document.getElementById('simulate-toggle').checked = false;
            
            // Select all papers
            toggleSelectAll(true);
            
            // Trigger run
            setTimeout(() => {
                const startBtn = document.getElementById('start-btn');
                if (startBtn && !startBtn.disabled) startBtn.click();
            }, 300);
        }

        // Tab switcher logic
        function switchTab(tabId, btn) {
            document.querySelectorAll(".tab-content").forEach(tab => tab.classList.remove("active"));
            document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
            
            document.getElementById(tabId).classList.add("active");
            btn.classList.add("active");
            
            // Reload specific tab data on switch
            if (tabId === "unity-tab") {
                loadAssetsStatus();
            } else if (tabId === "explorer-tab") {
                loadPapers();
            }
        }

        // Lightbox image viewer
        function openLightbox(imgSrc) {
            const modal = document.createElement("div");
            modal.style.position = "fixed";
            modal.style.top = "0";
            modal.style.left = "0";
            modal.style.width = "100vw";
            modal.style.height = "100vh";
            modal.style.background = "rgba(0, 0, 0, 0.95)";
            modal.style.display = "flex";
            modal.style.alignItems = "center";
            modal.style.justifyContent = "center";
            modal.style.zIndex = "1000";
            modal.style.cursor = "zoom-out";
            
            modal.innerHTML = `
                <img src="${imgSrc}" style="max-width: 90%; max-height: 90%; object-fit: contain; border-radius: 8px; box-shadow: 0 0 30px rgba(0,0,0,0.8); background:#fff; padding:10px;">
                <span style="position: absolute; top: 20px; right: 30px; color: #fff; font-size: 30px; font-weight: bold; cursor: pointer;">&times;</span>
            `;
            
            modal.onclick = () => document.body.removeChild(modal);
            document.body.appendChild(modal);
        }

        // HTML escaping
        function escapeHtml(text) {
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
    