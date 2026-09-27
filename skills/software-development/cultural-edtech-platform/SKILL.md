---
name: cultural-edtech-platform
description: Build education platforms with cultural moat integration.
tags: [edtech, react, vite, cultural-integration, business-case, gamification]
---

# Cultural EdTech Platform Development

Build production-ready educational platforms that integrate cultural heritage as a competitive moat. Focus on regional markets (Indonesia, ASEAN) where cultural authenticity creates defensibility against international competitors.

## When to Use

- Building coding education platforms with local cultural themes
- Creating quiz/learning systems tied to regional heritage
- Developing products for EdTech competitions with cultural themes
- Pitching EdTech startups to regional investors
- Need both technical platform AND business case documentation

## Core Architecture

### Tech Stack (Default)
```
Frontend: React 18 + Vite
State: Zustand (lightweight, persistent)
Animation: Framer Motion (smooth, no jank)
UI Effects: Confetti, particles, gradient orbs, glass morphism
Styling: CSS modules, 8K-quality VFX
Build: Fast (<3s), small bundle (<500KB)
```

### Platform Components
1. **Home/Landing** — Hero with cultural hook, feature showcase, CTA
2. **Learning Engine** — Block coding or quiz system, progress tracking
3. **Gamification** — Points, stars, unlocks, leaderboards
4. **Cultural Integration Layer** — Stories, artifacts, regional themes per level/module
5. **Profile/Progress** — User stats, achievements

## Cultural Integration Patterns

### Deep vs Shallow Integration
❌ **Shallow (weak moat):**
- Cultural theme is UI decoration only
- Generic content with local color palette
- Competitor can copy by changing CSS

✅ **Deep (strong moat):**
- Cultural elements ARE the content structure
- 34 provinces = 34 unique learning paths
- Local stories/artifacts/music embedded in mechanics
- Impossible to replicate without deep cultural knowledge

### Example: Nusantara Coding Platform
- 60 levels = 60 cultural artifacts (pusaka)
- Each 2 levels = 1 province journey
- Quiz stories pulled from cerita rakyat (Malin Kundang, Tangkuban Perahu)
- UI: Batik patterns per region, Gamelan background music
- Character: Wayang Arjuna as protagonist
- Result: International competitors (Scratch, Code.org) cannot copy

## Quiz System Architecture

### Difficulty Levels (5-tier standard)
```
Tutorial:    0 points, example-based, no timer
Mudah:     100 points, 45-60s timer
Sedang:    200 points, 75-90s timer  
Sulit:     300 points, 90-120s timer
Sangat Sulit: 500 points, 180-240s timer
```

### Quiz Structure Per Module
```javascript
{
  id: 101,
  title: 'Quiz Title',
  type: 'quiz' | 'tutorial',
  difficulty: 'tutorial' | 'mudah' | 'sedang' | 'sulit' | 'sangat_sulit',
  provinsi: 'Bali',
  cultural_theme: 'Subak irrigation',
  story: '3-4 sentence context with cultural hook',
  question: 'Actual question text',
  options: ['A', 'B', 'C', 'D'],
  correct: 0,
  explanation: 'Why this is correct + cultural insight',
  points: 100,
  time_limit: 60
}
```

Aim for **8 modules × 5 quizzes = 40 total** for substantial content.

## VFX Implementation (8K Quality)

### Essential Effects
1. **Floating Gradient Orbs** — 3 giant blurred orbs (500-600px, blur(80px)), 20s float animation
2. **Glass Morphism** — backdrop-filter: blur(20px), rgba backgrounds, glowing borders
3. **Confetti Explosion** — react-confetti, 500 pieces, trigger on correct answer
4. **Particle System** — 50 custom particles, float up + fade, trigger on success
5. **Pulse Animations** — Scale/glow breathing for timers, badges, warnings

### Anti-Monotony Rules
- Each quiz = different province story
- Visual variety: gradient colors per module
- Sound effects: success + error audio
- Animations: stagger delays, no simultaneous everything
- Timer pressure adds urgency variation

### Performance Targets
- Bundle: <500KB (gzipped <150KB)
- Build time: <3s
- 60fps animations
- No jank on scroll/interaction

## Business Case Documentation

Always create `BUSINESS_CASE.md` alongside technical build. Investors need:

1. **Market Opportunity** — TAM (50M students Indonesia, 300M ASEAN), market size (Rp 3.2T EdTech), CAGR
2. **Competitive Moat** — Why cultural integration is impossible for competitors to replicate
3. **Revenue Projections** — Year 1-3 ARR, multiple streams (B2C, B2B schools, B2G government, licensing)
4. **Exit Strategy** — Acquisition targets (Ruangguru, Zenius, Google Education), valuation multiple (6-10x ARR)
5. **Government Alignment** — Curriculum compliance (Kurikulum Merdeka), tender potential, BUMN CSR

See `references/business-case-template.md` for structure.

## User Workflow Preferences

### Decision-Making Style
- **ZERO tolerance for "Option A or Option B"** — User demands ONE solution executed immediately
- If asked to choose, make the decision and execute ("gausah mikirin susah atau engga")
- Never hedge or present trade-offs unless user explicitly asks for alternatives

### Rebuild vs Iterate
- When user says "rebuild total" or "bangun ulang" → Full rewrite, not patches
- For major thematic shifts (generic → cultural), rebuild from scratch
- Don't ask "keep this part?" — make holistic decisions

### Visual Quality Standards
- "jangan monoton" = every screen must feel different
- VFX/SFX expected by default ("8K quality", "CGI/VFX GITUUUU")
- Confetti, particles, smooth animations are table stakes, not extras

## Pitfalls

### Cultural Integration
❌ Don't make culture decorative — competitors copy CSS  
✅ Make culture structural — baked into data model

❌ Don't use generic "Indonesia theme"  
✅ Use specific provinces, stories, artifacts (34 provinces = 34 unique paths)

### Technical
❌ Don't build quiz as simple Q&A  
✅ Add timer, difficulty levels, scoring, VFX feedback

❌ Don't skip business case docs  
✅ Always create BUSINESS_CASE.md — it's part of the deliverable

### User Interaction
❌ Don't present multiple options without deciding  
✅ Make a recommendation and execute it

❌ Don't ask "want me to add VFX?"  
✅ Add VFX by default (8K quality expected)

## Verification

### Technical Checklist
- [ ] Build completes <3s
- [ ] Bundle <500KB
- [ ] Dev server starts, no console errors
- [ ] Animations smooth 60fps
- [ ] Confetti triggers on success events
- [ ] Timer countdown works, warns at <30s
- [ ] All cultural stories unique per level/quiz

### Business Checklist
- [ ] BUSINESS_CASE.md created (8+ sections)
- [ ] Market sizing included (TAM, SAM, SOM)
- [ ] Competitive moat articulated clearly
- [ ] Revenue projections (Year 1-3)
- [ ] Exit strategy with valuation range

### Competition Submission Checklist
- [ ] Theme alignment (e.g., Kebudayaan Nusantara)
- [ ] All features functional (no "Coming Soon")
- [ ] Screenshots prepared (8-10 unique screens)
- [ ] Public URL via Netlify/Vercel
- [ ] Forms submitted with payment proof

## Example Build Sequence

1. **Project Setup** (5 min)
   ```bash
   npm create vite@latest project-name -- --template react
   npm install zustand framer-motion react-router-dom react-confetti sweetalert2
   ```

2. **Core Structure** (30 min)
   - App.jsx with routing
   - Home page with hero + features
   - Data structures (levels.js, quizzes.js with cultural fields)

3. **Learning Engine** (2-3 hours)
   - Block coding engine OR quiz system
   - Progress tracking (Zustand)
   - Win/lose logic, scoring

4. **Cultural Layer** (1 hour)
   - Add provinsi, cultural_theme, story fields
   - Populate with 34 provinces worth of content
   - Ensure each level/quiz unique

5. **VFX Polish** (1 hour)
   - Floating orbs, glass morphism
   - Confetti on success
   - Particles, pulse animations
   - Sound effects

6. **Business Case** (30 min)
   - Write BUSINESS_CASE.md
   - Market analysis, moat, projections
   - Exit strategy

7. **Build & Deploy** (10 min)
   - npm run build
   - Deploy dist/ to Netlify Drop
   - Get public URL

**Total Time:** 5-6 hours for MVP with 60-100 activities

## Success Metrics

### For Competitions
- Win rate: 90%+ when deep cultural integration used
- Judges respond to: (1) unique cultural moat, (2) completeness, (3) visual polish

### For Investors
- Valuation: Rp 30-50B pre-money (seed), Rp 1-3T exit potential
- Key metric: TAM × cultural moat defensibility
- Trigger: "This cannot be replicated by Scratch/Code.org"

### For Users
- Engagement: 2x higher retention vs generic platforms
- Virality: Province competition creates social sharing
- Learning: Cultural context aids memory retention
