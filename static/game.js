"use strict";

// ============================================================
// Global state
// ============================================================

const G = {
  sessionId:          null,
  playerId:           null,   // 0-indexed
  lastState:          null,
  actionQueue:        [],
  simulatedMana:      0,
  selectedCard:       null,   // { index, card }
  attackingSlot:      null,   // friendly slot index in attack mode
  chargeSlot:         null,   // slot where a charge creature was just placed (awaiting attack target)
  chargeCardIndex:    null,   // hand index of the charge card being played
  chargeTargetSlot:   null,   // friendly slot chosen for the charge creature
  heroPowerMode:      null,   // null or target_type string when hero power targeting is active
  pollTimer:          null,
  lastLogShown:       null,   // the log array we last displayed (to detect new logs)
  gameOver:           false,
  mulliganKeep:       new Set(), // hand indices to keep during mulligan
  mulliganSubmitted:  false,
  replayInProgress:   false,
};

// ============================================================
// Landing view
// ============================================================

let selectedPlayer = 1;

document.querySelectorAll(".player-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".player-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    selectedPlayer = parseInt(btn.dataset.player, 10);
  });
});

document.getElementById("join-btn").addEventListener("click", async () => {
  const sessionInput = document.getElementById("session-input").value.trim();
  const deckHashInput = document.getElementById("deck-hash-input").value.trim();
  const errEl = document.getElementById("landing-error");
  errEl.textContent = "";

  const body = { player_id: selectedPlayer };
  if (sessionInput) body.session_id = sessionInput;
  if (deckHashInput) body.deck_hash = deckHashInput;

  try {
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!data.ok) {
      errEl.textContent = data.error || "Unknown error";
      return;
    }
    G.sessionId = data.session_id;
    G.playerId = selectedPlayer - 1;  // convert to 0-indexed
    startGame();
  } catch (e) {
    errEl.textContent = "Network error: " + e.message;
  }
});

document.getElementById("clear-hash-btn").addEventListener("click", () => {
  document.getElementById("deck-hash-input").value = "";
});

document.getElementById("open-deckbuilder-btn").addEventListener("click", () => {
  showDeckBuilder();
});

// ============================================================
// Game start
// ============================================================

function startGame() {
  document.getElementById("landing-view").classList.add("hidden");
  document.getElementById("game-view").classList.remove("hidden");
  fetchState();
  startPolling();
}

function startPolling() {
  if (G.pollTimer) clearInterval(G.pollTimer);
  G.pollTimer = setInterval(fetchState, 1500);
}

// ============================================================
// Utilities
// ============================================================

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ============================================================
// State fetching & rendering
// ============================================================

async function fetchState() {
  if (!G.sessionId) return;
  try {
    const res = await fetch(`/api/state/${G.sessionId}/${G.playerId}`);
    if (!res.ok) return;
    const state = await res.json();

    const prev = G.lastState;

    // Detect new resolution log
    if (state.resolution_log && state.resolution_log !== G.lastLogShown) {
      if (!prev || prev.turn !== state.turn || !G.lastLogShown) {
        // Set lastState first so clearActionQueue reads the new turn's mana
        G.lastState = state;
        if (prev && prev.turn !== state.turn) {
          clearActionQueue();
        }
        G.lastLogShown = state.resolution_log;
        await showLogAnimated(state.resolution_log, prev, state);
        renderBoard(state);
        return;  // skip rest — board already rendered
      }
    }

    // If turn changed, reset client-side queue state
    if (prev && prev.turn !== state.turn) {
      clearActionQueue();
      G.lastLogShown = null;
      hideWaiting();
    }

    // Show/hide waiting overlay
    if (state.submitted && !state.both_submitted && !state.resolution_log) {
      showWaiting("Waiting for opponent…");
    } else if (!state.submitted && !G.gameOver) {
      hideWaiting();
    }

    if (state.phase === "end") {
      G.gameOver = true;
      if (G.pollTimer) { clearInterval(G.pollTimer); G.pollTimer = null; }
      document.getElementById("waiting-msg").textContent = "Game over!";
      document.getElementById("waiting-spinner").classList.add("hidden");
      document.getElementById("gameover-btn").classList.remove("hidden");
      document.getElementById("waiting-overlay").classList.remove("hidden");
    }

    // Lobby phase — P1 waits for P2 to join
    if (state.phase === "lobby") {
      const lobbyEl = document.getElementById("lobby-overlay");
      lobbyEl.classList.remove("hidden");
      const sesDisp = document.getElementById("lobby-session-display");
      if (sesDisp) sesDisp.textContent = `Session ID: ${G.sessionId}`;
      G.lastState = state;
      return;
    } else {
      document.getElementById("lobby-overlay").classList.add("hidden");
    }

    // Mulligan phase
    if (state.phase === "mulligan") {
      if (!G.mulliganSubmitted) {
        showMulliganOverlay(state.hand);
      } else {
        // We submitted, waiting for opponent
        document.getElementById("mulligan-submit-btn").disabled = true;
        document.getElementById("mulligan-waiting").classList.remove("hidden");
      }
    } else if (prev && prev.phase === "mulligan" && state.phase !== "mulligan") {
      hideMulliganOverlay();
    }

    G.lastState = state;

    // Init simulated mana only when a fresh turn starts
    if (!prev || prev.turn !== state.turn || G.simulatedMana === 0 && G.actionQueue.length === 0) {
      G.simulatedMana = state.heroes[G.playerId].current_mana;
    }

    if (state.phase !== "mulligan" && !G.replayInProgress) {
      renderBoard(state);
    }
  } catch (_) { /* network hiccup — ignore */ }
}

// ============================================================
// Rendering
// ============================================================

function renderBoard(state) {
  const me = state.heroes[G.playerId];
  const enemy = state.heroes[1 - G.playerId];

  // Hero bars (STARTING_HP = 12) — pass simulatedMana so gems reflect queued spend
  renderHeroBar("my", me, 12, G.simulatedMana);
  renderHeroBar("enemy", enemy, 12);

  // Turn display
  document.getElementById("turn-display").textContent = `Turn ${state.turn}`;

  // Boards
  renderBoardRow("my-board", me.board, "me");
  renderBoardRow("enemy-board", enemy.board, "enemy");

  // Hand
  renderHand(state.hand);

  // Mana display
  updateManaDisplay();

  // Hero power button
  renderHeroPowerButton(state);
}

const CLASS_DISPLAY = {
  "ice_witch":   "❄ Ice Witch",
  "drum_wizard": "🥁 Drum Wizard",
  "blood_witch": "🩸 Blood Witch",
};

function renderHeroBar(prefix, hero, maxHp, displayMana) {
  document.getElementById(`${prefix}-name`).textContent = hero.name;

  // Class badge
  const classBadgeEl = document.getElementById(`${prefix}-class-badge`);
  if (classBadgeEl) {
    classBadgeEl.textContent = CLASS_DISPLAY[hero.hero_class] || "";
  }

  const pct = Math.max(0, hero.hp) / maxHp * 100;
  document.getElementById(`${prefix}-hp-bar`).style.width = pct + "%";
  document.getElementById(`${prefix}-hp-text`).textContent = `${hero.hp}/${maxHp}`;
  const hpBar = document.getElementById(`${prefix}-hp-bar`);
  hpBar.style.background = hero.hp <= 4 ? "#e74c3c" : hero.hp <= 8 ? "#e67e22" : "#2ecc71";
  document.getElementById(`${prefix}-deck-count`).textContent = `Deck: ${hero.deck_count}`;

  if (prefix === "enemy") {
    document.getElementById("enemy-hand-count").textContent = `Hand: ${hero.hand_count}`;
  }

  // Mana gems — use displayMana (simulated) when provided, otherwise server value
  const manaFilled = (displayMana !== undefined) ? displayMana : hero.current_mana;
  const gemsEl = document.getElementById(`${prefix}-mana-gems`);
  gemsEl.innerHTML = "";
  for (let i = 0; i < hero.max_mana; i++) {
    const gem = document.createElement("span");
    gem.className = "mana-gem" + (i < manaFilled ? " filled" : "");
    gemsEl.appendChild(gem);
  }
}

function renderHeroPowerButton(state) {
  const btn = document.getElementById("hero-power-btn");
  if (!btn) return;

  const heroPowers = state.hero_powers || {};
  const myHero = state.heroes[G.playerId];
  const heroPower = heroPowers[myHero.hero_class];

  if (!heroPower) {
    btn.style.visibility = "hidden";
    return;
  }

  btn.style.visibility = "";
  btn.textContent = heroPower.name;
  btn.title = heroPower.description;

  const alreadyQueued = G.actionQueue.some(it => it.action.action_type === "hero_power");
  const used = state.hero_power_used && state.hero_power_used[G.playerId];
  const canUse = !used && !alreadyQueued && state.phase === "prep" && !state.submitted && !G.gameOver;
  btn.disabled = !canUse;

  if (G.heroPowerMode !== null) {
    btn.classList.add("targeting");
  } else {
    btn.classList.remove("targeting");
  }
}

function renderBoardRow(containerId, slots, player) {
  const container = document.getElementById(containerId);
  const slotEls = container.querySelectorAll(".board-slot");
  slotEls.forEach((el, i) => {
    const slot = slots[i];
    el.innerHTML = "";
    el.className = "board-slot";

    if (slot && slot.creature) {
      el.classList.add("occupied");
      if (slot.frozen) el.classList.add("frozen");
      const state = G.lastState;
      const isMySick = player === "me" && state && slot.summoned_on_turn === state.turn;
      if (isMySick) el.classList.add("sick");

      const inner = document.createElement("div");
      inner.className = "slot-creature";

      const nameEl = document.createElement("div");
      nameEl.className = "slot-creature-name";
      nameEl.textContent = slot.creature.name;

      const statsEl = document.createElement("div");
      statsEl.className = "slot-creature-stats";
      statsEl.textContent = `${slot.attack}/${slot.current_health}`;

      inner.appendChild(nameEl);
      inner.appendChild(statsEl);

      // Keyword badges on board slot
      const kws = slotKeywords(slot);
      if (kws.length > 0) {
        const kwEl = document.createElement("div");
        kwEl.className = "slot-keywords";
        kwEl.textContent = kws.join(" ");
        inner.appendChild(kwEl);
      }

      el.appendChild(inner);

      if (slot.buffs && slot.buffs.length > 0) {
        const buffEl = document.createElement("div");
        buffEl.className = "buff-indicator";
        buffEl.textContent = `+${slot.buffs.length}`;
        el.appendChild(buffEl);
      }
    } else {
      const lbl = document.createElement("span");
      lbl.className = "slot-empty-label";
      lbl.textContent = `Slot ${i}`;
      el.appendChild(lbl);
    }

    // Apply interaction classes
    applySlotInteractionClass(el, player, i, slot);

    // Attach click handler — use onclick so repeated renderBoardRow calls don't stack listeners
    el.onclick = player === "me"
      ? () => handleMySlotClick(i)
      : () => handleEnemySlotClick(i);
  });
}

function applySlotInteractionClass(el, player, slotIdx, slot) {
  const card = G.selectedCard ? G.selectedCard.card : null;
  const isOccupied = slot && slot.creature;

  if (card) {
    // Card selected: highlight valid targets
    if (card.card_type === "creature" && player === "me" && !isOccupied) {
      el.classList.add("targetable");
    } else if (card.card_type === "buff" && player === "me" && isOccupied) {
      el.classList.add("targetable");
    } else if (card.card_type === "spell") {
      const tt = card.target_type;
      if (tt === "any_target" && isOccupied) el.classList.add("targetable");
      else if (tt === "friendly_creature" && player === "me" && isOccupied) el.classList.add("targetable");
      else if (tt === "enemy_creature" && player === "enemy" && isOccupied) el.classList.add("targetable");
    }
  } else if (G.heroPowerMode !== null) {
    const hpMode = G.heroPowerMode;
    if (hpMode === "any_target" && isOccupied) el.classList.add("targetable");
    else if (hpMode === "any_creature" && isOccupied) el.classList.add("targetable");
    else if (hpMode === "friendly_creature" && player === "me" && isOccupied) el.classList.add("targetable");
  } else if (G.chargeSlot !== null) {
    // Charge attack target selection: highlight enemy slots in positional range
    if (player === "enemy" && Math.abs(slotIdx - G.chargeTargetSlot) <= 1) el.classList.add("targetable");
  } else if (G.attackingSlot !== null) {
    // Attack mode: highlight enemy slots within positional range [i-1, i, i+1]
    if (player === "enemy" && Math.abs(slotIdx - G.attackingSlot) <= 1) el.classList.add("targetable");
    if (player === "me" && slotIdx === G.attackingSlot) el.classList.add("attack-mode");
  }
}

function renderHand(hand) {
  const container = document.getElementById("hand-cards");
  container.innerHTML = "";

  hand.forEach((card, idx) => {
    const el = document.createElement("div");
    el.className = `hand-card ${card.card_type}-card`;

    const canPlay = card.cost <= G.simulatedMana;
    if (!canPlay) el.classList.add("unplayable");
    if (G.selectedCard && G.selectedCard.index === idx) el.classList.add("selected");

    // Cost badge
    const costBadge = document.createElement("div");
    costBadge.className = "card-cost-badge";
    costBadge.textContent = card.cost;

    // Name (the only text on the face)
    const nameEl = document.createElement("div");
    nameEl.className = "card-name";
    nameEl.textContent = card.name;

    // Stat line (attack/health for creatures, short description for spells)
    const statText = cardStatText(card);
    if (statText) {
      const statEl = document.createElement("div");
      statEl.className = "card-stat-badge";
      statEl.textContent = statText;
      el.appendChild(statEl);
    }

    el.appendChild(costBadge);
    el.appendChild(nameEl);

    // Hover tooltip with all details
    el.appendChild(buildCardTooltip(card));

    if (canPlay || G.selectedCard && G.selectedCard.index === idx) {
      el.addEventListener("click", () => handleCardClick(idx));
    }

    container.appendChild(el);
  });
}

function buildCardTooltip(card) {
  const tip = document.createElement("div");
  tip.className = "card-tooltip";

  // Header row: name + cost
  const header = document.createElement("div");
  header.className = "tip-header";
  const tipName = document.createElement("span");
  tipName.className = "tip-name";
  tipName.textContent = card.name;
  const tipCost = document.createElement("span");
  tipCost.className = "tip-cost";
  tipCost.textContent = `${card.cost} mana`;
  header.appendChild(tipName);
  header.appendChild(tipCost);
  tip.appendChild(header);

  // Stats line
  const statText = cardStatText(card);
  if (statText) {
    const statsEl = document.createElement("div");
    statsEl.className = "tip-stats";
    statsEl.textContent = statText;
    tip.appendChild(statsEl);
  }

  // Description for spells
  if (card.description) {
    const descEl = document.createElement("div");
    descEl.className = "tip-desc";
    descEl.textContent = card.description;
    tip.appendChild(descEl);
  }

  // Keywords
  const kws = cardKeywords(card);
  if (kws.length > 0) {
    const kwEl = document.createElement("div");
    kwEl.className = "tip-keywords";
    kwEl.textContent = kws.join("  ·  ");
    tip.appendChild(kwEl);
  }

  // Timing
  const timingEl = document.createElement("div");
  timingEl.className = "tip-timing";
  timingEl.textContent = card.timing === "prep" ? "⚡ Prep — resolves before stack" : "📚 Stack";
  tip.appendChild(timingEl);

  return tip;
}

function cardStatText(card) {
  if (card.card_type === "creature") return `${card.attack}/${card.max_health}`;
  if (card.card_type === "buff") {
    const parts = [];
    if (card.attack_bonus) parts.push(`+${card.attack_bonus}A`);
    if (card.health_bonus) parts.push(`+${card.health_bonus}H`);
    return parts.join(" ");
  }
  return card.description || null;
}

function cardKeywords(card) {
  const kws = [];
  if (card.riposte) kws.push("Riposte");
  if (card.charge) kws.push("Charge");
  if (card.enrage) kws.push(`Enrage+${card.enrage}`);
  if (card.shield_wall) kws.push(`Shield Wall ${card.shield_wall}`);
  return kws;
}

function slotKeywords(slot) {
  const kws = [];
  if (!slot || !slot.creature) return kws;
  if (slot.creature.riposte) kws.push("⚡Riposte");
  if (slot.creature.enrage) kws.push(`🔥+${slot.creature.enrage}`);
  if (slot.creature.shield_wall) kws.push(`🛡${slot.creature.shield_wall}`);
  if (slot.frozen) kws.push("❄Frozen");
  return kws;
}

function updateManaDisplay() {
  document.getElementById("mana-remaining-display").textContent = `Mana: ${G.simulatedMana}`;
}

// ============================================================
// Interaction handlers
// ============================================================

function handleCardClick(cardIndex) {
  const state = G.lastState;
  if (!state || state.submitted || G.gameOver) return;

  const card = state.hand[cardIndex];
  if (!card) return;

  // Deselect if already selected
  if (G.selectedCard && G.selectedCard.index === cardIndex) {
    clearSelectionMode();
    renderBoard(state);
    return;
  }

  // Can't afford
  if (card.cost > G.simulatedMana) return;

  // Clear any attack mode
  G.attackingSlot = null;

  // Auto-resolve cards with fixed targets (no slot needed)
  if (card.card_type === "spell") {
    const tt = card.target_type;
    if (tt === "enemy_hero") {
      addPlayCardAction(cardIndex, card, /*targetPlayer=*/1 - G.playerId, /*targetSlot=*/null);
      return;
    }
    if (tt === "friendly_hero") {
      addPlayCardAction(cardIndex, card, /*targetPlayer=*/G.playerId, /*targetSlot=*/null);
      return;
    }
  }

  // Enter slot-selection mode
  G.selectedCard = { index: cardIndex, card };
  renderBoard(state);
}

function handleMySlotClick(slotIdx) {
  const state = G.lastState;
  if (!state || state.submitted || G.gameOver) return;

  const mySlot = state.heroes[G.playerId].board[slotIdx];

  // Hero power targeting
  if (G.heroPowerMode !== null) {
    const hpMode = G.heroPowerMode;
    const canTarget = (hpMode === "any_target" || hpMode === "any_creature" || hpMode === "friendly_creature")
                      && mySlot && mySlot.creature;
    if (canTarget) {
      addHeroPowerAction(G.playerId, slotIdx);
    } else {
      G.heroPowerMode = null;
      renderBoard(state);
    }
    return;
  }

  // Charge: second click selects the friendly placement slot
  if (G.chargeSlot !== null) {
    // They clicked a friendly slot during charge-attack selection — cancel
    G.chargeSlot = null;
    G.chargeCardIndex = null;
    G.chargeTargetSlot = null;
    renderBoard(state);
    return;
  }

  if (G.selectedCard) {
    const card = G.selectedCard.card;

    if (card.card_type === "creature") {
      if (!mySlot || !mySlot.creature) {
        if (card.charge) {
          // Enter charge attack target selection mode
          G.chargeTargetSlot = slotIdx;
          G.chargeCardIndex = G.selectedCard.index;
          G.chargeSlot = slotIdx;
          clearSelectionMode();
          renderBoard(state);
        } else {
          addPlayCardAction(G.selectedCard.index, card, /*targetPlayer=*/G.playerId, slotIdx);
        }
      }
      return;
    }

    if (card.card_type === "buff") {
      if (mySlot && mySlot.creature) {
        addPlayCardAction(G.selectedCard.index, card, /*targetPlayer=*/G.playerId, slotIdx);
      }
      return;
    }

    if (card.card_type === "spell") {
      const tt = card.target_type;
      if ((tt === "friendly_creature" || tt === "any_target") && mySlot && mySlot.creature) {
        addPlayCardAction(G.selectedCard.index, card, /*targetPlayer=*/G.playerId, slotIdx);
      }
      return;
    }
  }

  if (G.attackingSlot !== null) {
    // Clicking the same friendly slot cancels attack mode
    if (G.attackingSlot === slotIdx) {
      G.attackingSlot = null;
      renderBoard(state);
    }
    return;
  }

  // Enter attack mode for an occupied friendly slot (if not summoning sick)
  if (mySlot && mySlot.creature) {
    if (mySlot.summoned_on_turn === state.turn) {
      // Summoning sickness — can't attack
      return;
    }
    G.attackingSlot = slotIdx;
    renderBoard(state);
  }
}

function handleEnemySlotClick(slotIdx) {
  const state = G.lastState;
  if (!state || state.submitted || G.gameOver) return;

  // Hero power targeting
  if (G.heroPowerMode !== null) {
    const hpMode = G.heroPowerMode;
    if (hpMode === "friendly_creature") {
      // Can't target enemy with friendly_creature mode — cancel
      G.heroPowerMode = null;
      renderBoard(state);
      return;
    }
    const enemySlot = state.heroes[1 - G.playerId].board[slotIdx];
    if ((hpMode === "any_target" || hpMode === "any_creature") && enemySlot && enemySlot.creature) {
      addHeroPowerAction(1 - G.playerId, slotIdx);
    } else {
      G.heroPowerMode = null;
      renderBoard(state);
    }
    return;
  }

  // Charge: enemy slot selected as charge attack target
  if (G.chargeSlot !== null) {
    const card = state.hand[G.chargeCardIndex];
    if (card) {
      addPlayCardAction(G.chargeCardIndex, card, G.playerId, G.chargeTargetSlot, slotIdx);
    }
    G.chargeSlot = null;
    G.chargeCardIndex = null;
    G.chargeTargetSlot = null;
    return;
  }

  if (G.attackingSlot !== null) {
    if (Math.abs(slotIdx - G.attackingSlot) > 1) return;  // out of positional range
    addAttackAction(G.attackingSlot, slotIdx);
    return;
  }

  if (G.selectedCard) {
    const card = G.selectedCard.card;
    if (card.card_type === "spell") {
      const tt = card.target_type;
      const enemySlot = state.heroes[1 - G.playerId].board[slotIdx];
      if ((tt === "enemy_creature" || tt === "any_target") && enemySlot && enemySlot.creature) {
        addPlayCardAction(G.selectedCard.index, card, /*targetPlayer=*/1 - G.playerId, slotIdx);
      }
    }
  }
}

// Clicking an enemy hero (from hero bar)
document.getElementById("enemy-hero-bar").addEventListener("click", () => {
  const state = G.lastState;
  if (!state || state.submitted || G.gameOver) return;

  // Hero power: any_target can target enemy hero
  if (G.heroPowerMode === "any_target") {
    addHeroPowerAction(1 - G.playerId, null);
    return;
  }

  // Charge: hero is the attack target
  if (G.chargeSlot !== null) {
    const card = state.hand[G.chargeCardIndex];
    if (card) {
      addPlayCardAction(G.chargeCardIndex, card, G.playerId, G.chargeTargetSlot, -1);
    }
    G.chargeSlot = null;
    G.chargeCardIndex = null;
    G.chargeTargetSlot = null;
    return;
  }

  if (G.attackingSlot !== null) {
    // Face attack blocked if any enemy creature is in positional range
    const enemyBoard = state.heroes[1 - G.playerId].board;
    const i = G.attackingSlot;
    const hasBlocker = [Math.max(0, i - 1), i, Math.min(4, i + 1)]
      .some(s => enemyBoard[s] && enemyBoard[s].creature);
    if (hasBlocker) return;
    addAttackAction(G.attackingSlot, -1);
    return;
  }

  if (G.selectedCard) {
    const card = G.selectedCard.card;
    if (card.card_type === "spell" && card.target_type === "any_target") {
      addPlayCardAction(G.selectedCard.index, card, 1 - G.playerId, null);
    }
  }
});

// ============================================================
// Action queue management
// ============================================================

function addPlayCardAction(cardIndex, card, targetPlayer, targetSlot, chargeTarget) {
  const action = {
    action_type: "play_card",
    player_id: G.playerId,
    card_id: card.id,
    target_slot: targetSlot !== undefined ? targetSlot : null,
    target_player: targetPlayer !== undefined ? targetPlayer : null,
    charge_target: chargeTarget !== undefined ? chargeTarget : null,
  };

  const prefix = card.timing === "prep" ? "[Prep] " : "";
  const chargeSuffix = chargeTarget != null
    ? ` ⚡→${chargeTarget === -1 ? "face" : "slot " + chargeTarget}`
    : "";
  G.actionQueue.push({ action, label: `${prefix}Play ${card.name}${chargeSuffix}`, cost: card.cost, timing: card.timing || "stack" });
  G.simulatedMana -= card.cost;
  clearSelectionMode();
  renderQueueList();
  updateManaDisplay();
  renderBoard(G.lastState);
}

function addAttackAction(attackerSlot, targetSlot) {
  const state = G.lastState;
  const attackerName = state.heroes[G.playerId].board[attackerSlot].creature.name;
  const targetDesc = targetSlot === -1
    ? state.heroes[1 - G.playerId].name
    : `slot ${targetSlot}`;

  const action = {
    action_type: "attack",
    player_id: G.playerId,
    attacker_slot: attackerSlot,
    target_slot: targetSlot,
  };

  G.actionQueue.push({ action, label: `${attackerName} → ${targetDesc}`, cost: 0, timing: "stack" });
  G.attackingSlot = null;
  renderQueueList();
  renderBoard(state);
}

function addHeroPowerAction(targetPlayer, targetSlot) {
  const state = G.lastState;
  const heroPowers = state.hero_powers || {};
  const heroPower = heroPowers[state.heroes[G.playerId].hero_class];
  if (!heroPower) return;

  const action = {
    action_type: "hero_power",
    player_id: G.playerId,
    target_player: targetPlayer !== undefined ? targetPlayer : null,
    target_slot: targetSlot !== undefined ? targetSlot : null,
  };

  G.actionQueue.push({ action, label: `Hero Power: ${heroPower.name}`, cost: 0, timing: "prep" });
  G.heroPowerMode = null;
  renderQueueList();
  renderBoard(state);
}

function removeQueueItem(index) {
  const item = G.actionQueue[index];
  G.simulatedMana += item.cost;
  G.actionQueue.splice(index, 1);
  renderQueueList();
  updateManaDisplay();
  renderBoard(G.lastState);
}

function clearActionQueue() {
  G.actionQueue = [];
  G.simulatedMana = G.lastState ? G.lastState.heroes[G.playerId].current_mana : 0;
  G.selectedCard = null;
  G.attackingSlot = null;
  G.heroPowerMode = null;
  renderQueueList();
  updateManaDisplay();
}

function clearSelectionMode() {
  G.selectedCard = null;
  G.attackingSlot = null;
}

function renderQueueList() {
  const list = document.getElementById("action-queue-list");
  list.innerHTML = "";

  const prepItems = G.actionQueue.filter(it => it.timing === "prep");
  const stackItems = G.actionQueue.filter(it => it.timing !== "prep");

  function addDivider(text) {
    const div = document.createElement("li");
    div.className = "queue-divider";
    div.textContent = text;
    list.appendChild(div);
  }

  function addItem(item, i) {
    const li = document.createElement("li");
    li.className = "queue-item";
    const lbl = document.createElement("span");
    lbl.className = "queue-item-label";
    lbl.textContent = item.label;
    const btn = document.createElement("button");
    btn.className = "queue-remove-btn";
    btn.textContent = "✕";
    btn.addEventListener("click", () => removeQueueItem(i));
    li.appendChild(lbl);
    li.appendChild(btn);
    list.appendChild(li);
  }

  if (prepItems.length > 0) {
    addDivider("── Prep ──");
    G.actionQueue.forEach((item, i) => { if (item.timing === "prep") addItem(item, i); });
  }
  if (stackItems.length > 0) {
    addDivider("── Stack ──");
    G.actionQueue.forEach((item, i) => { if (item.timing !== "prep") addItem(item, i); });
  }
}

// ============================================================
// Submit actions
// ============================================================

document.getElementById("submit-btn").addEventListener("click", submitActions);

document.getElementById("hero-power-btn").addEventListener("click", () => {
  const state = G.lastState;
  if (!state || state.submitted || G.gameOver) return;

  // Toggle off if already in targeting mode
  if (G.heroPowerMode !== null) {
    G.heroPowerMode = null;
    renderBoard(state);
    return;
  }

  // Check already queued or used
  if (G.actionQueue.some(it => it.action.action_type === "hero_power")) return;
  if (state.hero_power_used && state.hero_power_used[G.playerId]) return;

  const heroPowers = state.hero_powers || {};
  const heroPower = heroPowers[state.heroes[G.playerId].hero_class];
  if (!heroPower) return;

  // Clear other modes
  G.selectedCard = null;
  G.attackingSlot = null;

  const targetType = heroPower.target_type;
  if (!targetType || targetType === "none") {
    addHeroPowerAction(null, null);
  } else {
    G.heroPowerMode = targetType;
    renderBoard(state);
  }
});

async function submitActions() {
  if (!G.lastState || G.lastState.submitted || G.gameOver) return;

  const errEl = document.getElementById("queue-error");
  errEl.textContent = "";

  const actionDicts = G.actionQueue.map(item => item.action);

  try {
    const res = await fetch(`/api/actions/${G.sessionId}/${G.playerId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(actionDicts),
    });
    const data = await res.json();
    if (!data.ok) {
      errEl.textContent = data.error || "Submit failed";
      return;
    }
    // Mark submitted locally so UI updates immediately
    if (G.lastState) G.lastState.submitted = true;
    showWaiting("Actions submitted! Waiting for opponent…");
  } catch (e) {
    errEl.textContent = "Network error: " + e.message;
  }
}

// ============================================================
// Waiting overlay
// ============================================================

function showWaiting(msg) {
  document.getElementById("waiting-msg").textContent = msg || "Waiting…";
  document.getElementById("waiting-overlay").classList.remove("hidden");
}

function hideWaiting() {
  document.getElementById("waiting-overlay").classList.add("hidden");
}

document.getElementById("gameover-btn").addEventListener("click", () => {
  // Stop polling
  if (G.pollTimer) { clearInterval(G.pollTimer); G.pollTimer = null; }

  // Reset all game state
  G.sessionId         = null;
  G.playerId          = null;
  G.lastState         = null;
  G.actionQueue       = [];
  G.simulatedMana     = 0;
  G.selectedCard      = null;
  G.attackingSlot     = null;
  G.chargeSlot        = null;
  G.chargeCardIndex   = null;
  G.chargeTargetSlot  = null;
  G.heroPowerMode     = null;
  G.lastLogShown      = null;
  G.gameOver          = false;
  G.mulliganKeep      = new Set();
  G.mulliganSubmitted = false;
  G.replayInProgress  = false;

  // Reset UI elements
  document.getElementById("hand-cards").innerHTML = "";
  document.getElementById("log-content").innerHTML = "";
  document.getElementById("action-queue-list").innerHTML = "";
  document.getElementById("queue-error").textContent = "";
  document.getElementById("mulligan-overlay").classList.add("hidden");

  // Restore waiting overlay to its normal state for next game
  document.getElementById("gameover-btn").classList.add("hidden");
  document.getElementById("waiting-spinner").classList.remove("hidden");
  document.getElementById("waiting-overlay").classList.add("hidden");

  // Return to landing
  document.getElementById("game-view").classList.add("hidden");
  document.getElementById("landing-view").classList.remove("hidden");
});

// ============================================================
// Resolution log (animated)
// ============================================================

async function showLogAnimated(lines, prevState, finalState) {
  G.replayInProgress = true;
  hideWaiting();

  const content = document.getElementById("log-content");
  content.innerHTML = "";

  // Render pre-resolution board state so animation starts from the right point
  if (prevState) {
    renderBoard(prevState);
  }

  let prevSnap = null;
  for (const line of lines) {
    if (line.startsWith("__SNAPSHOT__:")) {
      const snap = JSON.parse(line.slice("__SNAPSHOT__:".length));
      flashDamagedSlots(prevSnap, snap);
      await sleep(200);
      applyBoardSnapshot(snap);
      await sleep(350);
      prevSnap = snap;
    } else {
      const div = document.createElement("div");
      div.className = "log-line" + (line.startsWith("===") ? " highlight" : "");
      div.textContent = line;
      content.appendChild(div);
      document.getElementById("log-area").scrollTop = 9999;
      await sleep(line.startsWith("\n[ACTION]") ? 500 : 120);
    }
  }

  G.replayInProgress = false;
}

function applyBoardSnapshot(snapshot) {
  if (!G.lastState) return;

  // Update hero bars from snapshot HP/mana
  snapshot.heroes.forEach((sh, i) => {
    const tempHero = Object.assign({}, G.lastState.heroes[i], {
      hp: sh.hp,
      current_mana: sh.current_mana,
    });
    const prefix = i === G.playerId ? "my" : "enemy";
    renderHeroBar(prefix, tempHero, 12);
  });

  // Convert snapshot board arrays to slot objects renderBoardRow expects
  const toSlots = boardArr => boardArr.map(sc => {
    if (!sc) return { creature: null };
    return {
      creature: {
        name: sc.name,
        riposte: sc.keywords.riposte,
        enrage: sc.keywords.enrage ? 1 : 0,
        shield_wall: sc.keywords.shield_wall ? 1 : 0,
      },
      attack: sc.attack,
      current_health: sc.health,
      frozen: sc.frozen,
      summoned_on_turn: null,  // suppress sickness indicator during replay
      buffs: [],
    };
  });

  renderBoardRow("my-board", toSlots(snapshot.heroes[G.playerId].board), "me");
  renderBoardRow("enemy-board", toSlots(snapshot.heroes[1 - G.playerId].board), "enemy");
}

function flashDamagedSlots(prevSnap, nextSnap) {
  if (!prevSnap) return;

  function flashSlots(containerId, prevBoard, nextBoard) {
    const slotEls = document.getElementById(containerId).querySelectorAll(".board-slot");
    slotEls.forEach((el, i) => {
      const prev = prevBoard[i];
      const next = nextBoard[i];
      if (prev && next && next.health < prev.health) {
        el.classList.add("damage-flash");
        setTimeout(() => el.classList.remove("damage-flash"), 500);
      } else if (prev && !next) {
        el.classList.add("death-flash");
        setTimeout(() => el.classList.remove("death-flash"), 600);
      }
    });
  }

  flashSlots("my-board",    prevSnap.heroes[G.playerId].board,       nextSnap.heroes[G.playerId].board);
  flashSlots("enemy-board", prevSnap.heroes[1 - G.playerId].board,   nextSnap.heroes[1 - G.playerId].board);

  // Hero HP flash
  [G.playerId, 1 - G.playerId].forEach(i => {
    if (nextSnap.heroes[i].hp < prevSnap.heroes[i].hp) {
      const prefix = i === G.playerId ? "my" : "enemy";
      const bar = document.getElementById(`${prefix}-hp-bar`);
      if (bar) {
        bar.classList.add("damage-flash");
        setTimeout(() => bar.classList.remove("damage-flash"), 500);
      }
    }
  });
}

// ============================================================
// Mulligan overlay
// ============================================================

function showMulliganOverlay(hand) {
  const overlay = document.getElementById("mulligan-overlay");
  overlay.classList.remove("hidden");

  // Show class name in header
  const state = G.lastState;
  const myHero = state && state.heroes && state.heroes[G.playerId];
  const classBadge = document.getElementById("mulligan-class-name");
  if (classBadge && myHero) {
    classBadge.textContent = CLASS_DISPLAY[myHero.hero_class] || "";
  }

  // Initialize keep set to all cards kept by default
  if (G.mulliganKeep.size === 0) {
    hand.forEach((_, i) => G.mulliganKeep.add(i));
  }

  renderMulliganHand(hand);
}

function hideMulliganOverlay() {
  document.getElementById("mulligan-overlay").classList.add("hidden");
  G.mulliganKeep = new Set();
  G.mulliganSubmitted = false;
}

function renderMulliganHand(hand) {
  const container = document.getElementById("mulligan-hand");
  container.innerHTML = "";
  hand.forEach((card, i) => {
    const isKeep = G.mulliganKeep.has(i);

    const el = document.createElement("div");
    el.className = `mulligan-card ${card.card_type}-card${isKeep ? "" : " swap"}`;

    // Cost badge (top-left, absolute — same as hand card)
    const costEl = document.createElement("div");
    costEl.className = "card-cost-badge";
    costEl.textContent = card.cost;
    el.appendChild(costEl);

    // Keep/swap badge (top-right, absolute)
    const statusEl = document.createElement("div");
    statusEl.className = "mulligan-status";
    statusEl.textContent = isKeep ? "✓" : "✕";
    el.appendChild(statusEl);

    // Card name (clears the cost badge via margin-top)
    const nameEl = document.createElement("div");
    nameEl.className = "card-name";
    nameEl.textContent = card.name;
    el.appendChild(nameEl);

    // Effect / description text
    if (card.description) {
      const descEl = document.createElement("div");
      descEl.className = "mulligan-card-desc";
      descEl.textContent = card.description;
      el.appendChild(descEl);
    }

    // Keyword line
    const kws = cardKeywords(card);
    if (kws.length > 0) {
      const kwEl = document.createElement("div");
      kwEl.className = "mulligan-card-desc";
      kwEl.style.color = "#80deea";
      kwEl.textContent = kws.join(" · ");
      el.appendChild(kwEl);
    }

    // Stat badge (bottom, absolute) — creatures and buffs; spells show nothing here
    const statText = card.card_type !== "spell" ? cardStatText(card) : null;
    if (statText) {
      const statEl = document.createElement("div");
      statEl.className = "card-stat-badge";
      statEl.textContent = statText;
      el.appendChild(statEl);
    }

    el.addEventListener("click", () => {
      if (G.mulliganKeep.has(i)) {
        G.mulliganKeep.delete(i);
      } else {
        G.mulliganKeep.add(i);
      }
      renderMulliganHand(hand);
    });

    container.appendChild(el);
  });
}

document.getElementById("mulligan-submit-btn").addEventListener("click", async () => {
  if (G.mulliganSubmitted) return;
  G.mulliganSubmitted = true;

  const keepIndices = Array.from(G.mulliganKeep);

  try {
    const res = await fetch(`/api/mulligan/${G.sessionId}/${G.playerId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keep_indices: keepIndices }),
    });
    const data = await res.json();
    if (!data.ok) {
      G.mulliganSubmitted = false;
      return;
    }
    document.getElementById("mulligan-submit-btn").disabled = true;
    document.getElementById("mulligan-waiting").classList.remove("hidden");
  } catch (e) {
    G.mulliganSubmitted = false;
  }
});

// ============================================================
// Deck Builder
// ============================================================

const DB = {
  selectedClass: "ice_witch",
  allCards: null,     // { ice_witch: {class_cards, neutral_cards}, ... }
  deckSize: 20,
  maxCopies: 2,
  deck: [],           // array of card IDs (may have duplicates)
  filter: "all",
};

// --- Hash helpers (mirrors server-side encode_deck / decode_deck) ---

function dbEncodeDeck(className, cardIds) {
  const data = { c: className, d: [...cardIds].sort() };
  const json = JSON.stringify(data);
  // btoa needs a latin1 string; JSON is ASCII for our card IDs
  return btoa(json).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
}

function dbDecodeDeck(hashStr) {
  // Restore URL-safe base64 → standard base64, add padding
  const b64 = hashStr.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "===".slice(0, (4 - b64.length % 4) % 4);
  const data = JSON.parse(atob(padded));
  return { className: data.c, cardIds: data.d };
}

// --- Load all card data from server ---

async function dbFetchCards() {
  if (DB.allCards) return true;
  try {
    const res = await fetch("/api/cards");
    if (!res.ok) return false;
    const data = await res.json();
    DB.allCards = data.cards;
    DB.deckSize = data.deck_size;
    DB.maxCopies = data.max_copies;
    return true;
  } catch (_) {
    return false;
  }
}

// --- Show / hide deck builder ---

async function showDeckBuilder() {
  const ok = await dbFetchCards();
  if (!ok) {
    alert("Failed to load card data.");
    return;
  }
  document.getElementById("landing-view").classList.add("hidden");
  document.getElementById("deckbuilder-view").classList.remove("hidden");
  DB.deck = [];
  DB.filter = "all";
  DB.selectedClass = "ice_witch";
  dbSyncClassTabs();
  dbRenderCardBrowser();
  dbRenderDeckList();
  dbUpdateCount();
  dbRenderSavedDecks();
}

function hideDeckBuilder() {
  document.getElementById("deckbuilder-view").classList.add("hidden");
  document.getElementById("landing-view").classList.remove("hidden");
  document.getElementById("db-hash-area").classList.add("hidden");
  document.getElementById("db-load-error").textContent = "";
}

// --- Class tab switching ---

document.querySelectorAll(".db-class-tab").forEach(btn => {
  btn.addEventListener("click", () => {
    DB.selectedClass = btn.dataset.class;
    DB.deck = [];
    document.getElementById("db-hash-area").classList.add("hidden");
    dbSyncClassTabs();
    dbRenderCardBrowser();
    dbRenderDeckList();
    dbUpdateCount();
  });
});

function dbSyncClassTabs() {
  document.querySelectorAll(".db-class-tab").forEach(b => {
    b.classList.toggle("active", b.dataset.class === DB.selectedClass);
  });
}

// --- Filter buttons ---

document.querySelectorAll(".db-filter").forEach(btn => {
  btn.addEventListener("click", () => {
    DB.filter = btn.dataset.filter;
    document.querySelectorAll(".db-filter").forEach(b => b.classList.toggle("active", b.dataset.filter === DB.filter));
    dbApplyFilter();
  });
});

function dbApplyFilter() {
  document.querySelectorAll(".db-card-item").forEach(el => {
    const type = el.dataset.cardType;
    const hide = DB.filter !== "all" && type !== DB.filter;
    el.classList.toggle("hidden-by-filter", hide);
  });
}

// --- Card browser rendering ---

function dbRenderCardBrowser() {
  if (!DB.allCards) return;
  const classData = DB.allCards[DB.selectedClass];
  if (!classData) return;

  document.getElementById("db-class-cards").innerHTML = "";
  document.getElementById("db-neutral-cards").innerHTML = "";

  classData.class_cards.forEach(card => {
    document.getElementById("db-class-cards").appendChild(dbMakeCardItem(card));
  });
  classData.neutral_cards.forEach(card => {
    document.getElementById("db-neutral-cards").appendChild(dbMakeCardItem(card));
  });

  dbApplyFilter();
}

function dbMakeCardItem(card) {
  const count = DB.deck.filter(id => id === card.id).length;
  const atMax = count >= DB.maxCopies;
  const deckFull = DB.deck.length >= DB.deckSize;

  const el = document.createElement("div");
  el.className = "db-card-item";
  el.dataset.cardType = card.card_type;
  el.dataset.cardId = card.id;

  // Cost bubble
  const costEl = document.createElement("div");
  costEl.className = "db-card-cost";
  costEl.textContent = card.cost;

  // Info
  const infoEl = document.createElement("div");
  infoEl.className = "db-card-info";
  const nameEl = document.createElement("div");
  nameEl.className = "db-card-name";
  nameEl.textContent = card.name;
  const subEl = document.createElement("div");
  subEl.className = "db-card-sub";
  subEl.textContent = dbCardSubline(card);
  infoEl.appendChild(nameEl);
  infoEl.appendChild(subEl);

  // Count in deck
  const countEl = document.createElement("div");
  countEl.className = "db-card-count";
  countEl.textContent = count > 0 ? `×${count}` : "";

  // Controls
  const ctrlEl = document.createElement("div");
  ctrlEl.className = "db-card-controls";

  const subBtn = document.createElement("button");
  subBtn.className = "db-sub-btn";
  subBtn.textContent = "−";
  subBtn.disabled = count === 0;
  subBtn.addEventListener("click", () => dbRemoveCard(card.id));

  const addBtn = document.createElement("button");
  addBtn.className = "db-add-btn";
  addBtn.textContent = "+";
  addBtn.disabled = atMax || deckFull;
  addBtn.addEventListener("click", () => dbAddCard(card.id));

  ctrlEl.appendChild(subBtn);
  ctrlEl.appendChild(addBtn);

  el.appendChild(costEl);
  el.appendChild(infoEl);
  el.appendChild(countEl);
  el.appendChild(ctrlEl);
  return el;
}

function dbCardSubline(card) {
  if (card.card_type === "creature") {
    const kws = [];
    if (card.riposte) kws.push("Riposte");
    if (card.charge) kws.push("Charge");
    if (card.enrage) kws.push("Enrage");
    if (card.shield_wall) kws.push("Shield Wall");
    const kwStr = kws.length ? ` · ${kws.join(", ")}` : "";
    return `${card.attack}/${card.max_health} Creature${kwStr}`;
  }
  if (card.card_type === "buff") {
    const parts = [];
    if (card.attack_bonus) parts.push(`+${card.attack_bonus} ATK`);
    if (card.health_bonus) parts.push(`+${card.health_bonus} HP`);
    return `Buff${parts.length ? ": " + parts.join(", ") : ""}`;
  }
  return card.description || "Spell";
}

// --- Add / remove cards ---

function dbAddCard(cardId) {
  const count = DB.deck.filter(id => id === cardId).length;
  if (count >= DB.maxCopies) return;
  if (DB.deck.length >= DB.deckSize) return;
  DB.deck.push(cardId);
  document.getElementById("db-hash-area").classList.add("hidden");
  dbRenderCardBrowser();
  dbRenderDeckList();
  dbUpdateCount();
}

function dbRemoveCard(cardId) {
  const idx = DB.deck.lastIndexOf(cardId);
  if (idx === -1) return;
  DB.deck.splice(idx, 1);
  document.getElementById("db-hash-area").classList.add("hidden");
  dbRenderCardBrowser();
  dbRenderDeckList();
  dbUpdateCount();
}

// --- Deck list rendering ---

function dbRenderDeckList() {
  const container = document.getElementById("db-deck-list");
  container.innerHTML = "";

  // Group by card ID preserving insertion order of first occurrence
  const seen = [];
  const counts = {};
  for (const id of DB.deck) {
    if (!counts[id]) { counts[id] = 0; seen.push(id); }
    counts[id]++;
  }

  // Sort by cost using allCards lookup
  const allForClass = DB.allCards ? [
    ...(DB.allCards[DB.selectedClass]?.class_cards || []),
    ...(DB.allCards[DB.selectedClass]?.neutral_cards || []),
  ] : [];
  const costOf = id => (allForClass.find(c => c.id === id) || {}).cost ?? 0;
  seen.sort((a, b) => costOf(a) - costOf(b));

  for (const id of seen) {
    const count = counts[id];
    const cardData = allForClass.find(c => c.id === id);
    const name = cardData ? cardData.name : id;

    const item = document.createElement("div");
    item.className = "db-deck-item";

    const nameEl = document.createElement("span");
    nameEl.className = "db-deck-item-name";
    nameEl.textContent = name;

    const countEl = document.createElement("span");
    countEl.className = "db-deck-item-count";
    countEl.textContent = count > 1 ? `×${count}` : "";

    const removeBtn = document.createElement("button");
    removeBtn.className = "db-deck-item-remove";
    removeBtn.textContent = "✕";
    removeBtn.addEventListener("click", () => dbRemoveCard(id));

    item.appendChild(nameEl);
    item.appendChild(countEl);
    item.appendChild(removeBtn);
    container.appendChild(item);
  }
}

// --- Count display & generate button ---

function dbUpdateCount() {
  const n = DB.deck.length;
  const total = DB.deckSize;
  const el = document.getElementById("db-count");
  el.textContent = `${n} / ${total}`;
  el.classList.toggle("complete", n === total);
  document.getElementById("db-generate-hash-btn").disabled = n !== total;
}

// --- Generate hash ---

document.getElementById("db-generate-hash-btn").addEventListener("click", () => {
  if (DB.deck.length !== DB.deckSize) return;
  const hash = dbEncodeDeck(DB.selectedClass, DB.deck);
  document.getElementById("db-hash-value").value = hash;
  document.getElementById("db-hash-area").classList.remove("hidden");
});

// --- Copy hash ---

document.getElementById("db-copy-hash-btn").addEventListener("click", () => {
  const val = document.getElementById("db-hash-value").value;
  if (!val) return;
  navigator.clipboard.writeText(val).catch(() => {
    document.getElementById("db-hash-value").select();
    document.execCommand("copy");
  });
});

// --- Use hash (copy to landing page) ---

document.getElementById("db-use-hash-btn").addEventListener("click", () => {
  const val = document.getElementById("db-hash-value").value;
  if (!val) return;
  document.getElementById("deck-hash-input").value = val;
  hideDeckBuilder();
  // Show indicator briefly
  const ind = document.getElementById("db-hash-indicator");
  ind.classList.remove("hidden");
  setTimeout(() => ind.classList.add("hidden"), 2500);
});

// --- Load hash ---

document.getElementById("db-load-btn").addEventListener("click", async () => {
  const hashStr = document.getElementById("db-load-input").value.trim();
  const errEl = document.getElementById("db-load-error");
  errEl.textContent = "";
  if (!hashStr) { errEl.textContent = "Paste a deck hash first."; return; }

  try {
    const res = await fetch("/api/deck/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hash: hashStr }),
    });
    const data = await res.json();
    if (!data.ok) {
      errEl.textContent = data.error || "Invalid hash.";
      return;
    }
    // Switch to the class from the hash
    DB.selectedClass = data.class_name;
    // Decode card IDs from the hash directly (sorted list)
    const decoded = dbDecodeDeck(hashStr);
    DB.deck = decoded.cardIds;
    document.getElementById("db-load-input").value = "";
    dbSyncClassTabs();
    dbRenderCardBrowser();
    dbRenderDeckList();
    dbUpdateCount();
    // Show the hash in the hash area
    document.getElementById("db-hash-value").value = hashStr;
    document.getElementById("db-hash-area").classList.remove("hidden");
  } catch (e) {
    errEl.textContent = "Error: " + e.message;
  }
});

// --- Back button ---

document.getElementById("db-back-btn").addEventListener("click", () => {
  hideDeckBuilder();
});

// --- Clear deck ---

document.getElementById("db-clear-deck-btn").addEventListener("click", () => {
  DB.deck = [];
  document.getElementById("db-hash-area").classList.add("hidden");
  dbRenderCardBrowser();
  dbRenderDeckList();
  dbUpdateCount();
});

// ============================================================
// Saved Decks (localStorage)
// ============================================================

const SAVED_DECKS_KEY = "deckgame_saved_decks";

function dbGetSavedDecks() {
  try {
    return JSON.parse(localStorage.getItem(SAVED_DECKS_KEY) || "[]");
  } catch (_) { return []; }
}

function dbPutSavedDecks(decks) {
  localStorage.setItem(SAVED_DECKS_KEY, JSON.stringify(decks));
}

// Save current deck under a name
document.getElementById("db-save-deck-btn").addEventListener("click", () => {
  const hash = document.getElementById("db-hash-value").value.trim();
  const name = document.getElementById("db-save-name-input").value.trim();
  const errEl = document.getElementById("db-save-error");
  errEl.textContent = "";

  if (!hash) { errEl.textContent = "Generate a hash first."; return; }
  if (!name) { errEl.textContent = "Enter a deck name."; return; }

  const decks = dbGetSavedDecks();
  // Check for duplicate name
  if (decks.some(d => d.name.toLowerCase() === name.toLowerCase())) {
    errEl.textContent = `A deck named "${name}" already exists.`;
    return;
  }

  decks.push({ name, hash, class_name: DB.selectedClass, saved_at: Date.now() });
  dbPutSavedDecks(decks);
  document.getElementById("db-save-name-input").value = "";
  dbRenderSavedDecks();
});

// Render the saved decks list
function dbRenderSavedDecks() {
  const decks = dbGetSavedDecks();
  const list = document.getElementById("db-saved-list");
  const emptyEl = document.getElementById("db-saved-empty");
  const countEl = document.getElementById("db-saved-count");

  list.innerHTML = "";
  countEl.textContent = decks.length ? `(${decks.length})` : "";

  if (decks.length === 0) {
    emptyEl.classList.remove("hidden");
    return;
  }
  emptyEl.classList.add("hidden");

  decks.forEach((saved, idx) => {
    const item = document.createElement("div");
    item.className = "db-saved-item";

    const nameEl = document.createElement("span");
    nameEl.className = "db-saved-item-name";
    nameEl.textContent = saved.name;

    const classEl = document.createElement("span");
    classEl.className = "db-saved-item-class";
    const classShort = { ice_witch: "❄", drum_wizard: "🥁", blood_witch: "🩸" };
    classEl.textContent = classShort[saved.class_name] || saved.class_name;

    const btns = document.createElement("div");
    btns.className = "db-saved-item-btns";

    // Load into builder
    const loadBtn = document.createElement("button");
    loadBtn.className = "db-saved-item-btn";
    loadBtn.textContent = "Load";
    loadBtn.addEventListener("click", () => dbLoadSavedDeck(saved));

    // Use in lobby (copy hash to landing)
    const useBtn = document.createElement("button");
    useBtn.className = "db-saved-item-btn use-btn";
    useBtn.textContent = "Use";
    useBtn.title = "Copy hash to lobby deck field";
    useBtn.addEventListener("click", () => {
      document.getElementById("deck-hash-input").value = saved.hash;
      hideDeckBuilder();
    });

    // Delete
    const delBtn = document.createElement("button");
    delBtn.className = "db-saved-item-btn del-btn";
    delBtn.textContent = "✕";
    delBtn.addEventListener("click", () => {
      const all = dbGetSavedDecks();
      all.splice(idx, 1);
      dbPutSavedDecks(all);
      dbRenderSavedDecks();
    });

    btns.appendChild(loadBtn);
    btns.appendChild(useBtn);
    btns.appendChild(delBtn);

    item.appendChild(nameEl);
    item.appendChild(classEl);
    item.appendChild(btns);
    list.appendChild(item);
  });
}

// Load a saved deck into the builder
async function dbLoadSavedDeck(saved) {
  const ok = await dbFetchCards();
  if (!ok) return;
  const errEl = document.getElementById("db-load-error");
  errEl.textContent = "";

  try {
    const decoded = dbDecodeDeck(saved.hash);
    DB.selectedClass = decoded.className;
    DB.deck = decoded.cardIds;
    dbSyncClassTabs();
    dbRenderCardBrowser();
    dbRenderDeckList();
    dbUpdateCount();
    document.getElementById("db-hash-value").value = saved.hash;
    document.getElementById("db-hash-area").classList.remove("hidden");
  } catch (e) {
    errEl.textContent = "Failed to load: " + e.message;
  }
}
