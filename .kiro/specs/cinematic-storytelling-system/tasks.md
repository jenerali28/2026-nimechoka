# Implementation Tasks: Cinematic Storytelling System

## Overview
Simple, focused implementation to make video scenes flow together like a movie instead of looking random.

**Core Goal**: Enhance prompts with story context so each scene connects to the previous one.

---

## Phase 1: Basic Story Context System


### Task 1: Create Simple Story Context Tracker
- [x] 1.1 Create `utils/story_context.py` module
  - [x] 1.1.1 Read script file to understand story progression
  - [x] 1.1.2 Track what happened in previous scene (location, characters, action)
  - [x] 1.1.3 Identify emotional tone of each scene (tense, calm, dramatic, etc.)
  - [x] 1.1.4 Store simple context: "Previous scene: [location], [characters], [what happened]"

### Task 2: Enhance Prompts with Story Flow
- [x] 2.1 Create `utils/enhance_prompts.py` module
  - [x] 2.1.1 Read existing prompts.yaml file
  - [x] 2.1.2 For each scene, add context from previous scene to the prompt
  - [x] 2.1.3 Add transition hints: "Continuing from [previous scene context]..."
  - [x] 2.1.4 Keep character descriptions consistent across scenes
  - [x] 2.1.5 Make sure enhanced prompts stay under 950 characters
  - [x] 2.1.6 Write enhanced prompts back to prompts.yaml

### Task 3: Integrate with Existing Pipeline
- [x] 3.1 Modify `utils/multimodal_orchestrator.py`
  - [x] 3.1.1 After generating base prompts, call story context enhancement
  - [x] 3.1.2 Pass script file to enhancement function
  - [x] 3.1.3 Add simple flag to enable/disable (default: enabled)
  - [x] 3.1.4 Test with existing Egyptian Concubine example

---

## Phase 2: Character Consistency (Simple Version)

### Task 4: Track Character Appearance
- [x] 4.1 Extend `utils/story_context.py`
  - [x] 4.1.1 Extract character descriptions from prompts.yaml
  - [x] 4.1.2 Store each character's appearance (from character_profile)
  - [x] 4.1.3 When character appears in new scene, inject their consistent description
  - [x] 4.1.4 Example: "The Protagonist (thin black stick figure, long dark hair, olive face, white dress) continues..."

### Task 5: Simple Transition Logic
- [x] 5.1 Extend `utils/enhance_prompts.py`
  - [x] 5.1.1 If location changes between scenes, add "Scene shifts to [new location]"
  - [x] 5.1.2 If same location, add "Still in [location]"
  - [x] 5.1.3 If emotional tone changes dramatically, add visual cue (lighting change, camera shift)
  - [x] 5.1.4 Keep it simple - just 1-2 sentences of context

---

## Phase 3: Testing and Refinement

### Task 6: Test with Real Example
- [-] 6.1 Run on Egyptian Concubine video
  - [x] 6.1.1 Generate enhanced prompts
  - [ ] 6.1.2 Generate videos with enhanced prompts
  - [ ] 6.1.3 Compare before/after visual flow
  - [ ] 6.1.4 Check if scenes feel more connected

### Task 7: Simple Documentation
- [ ] 7.1 Create `docs/STORY_FLOW.md`
  - [ ] 7.1.1 Explain what the system does (adds story context to prompts)
  - [ ] 7.1.2 Show before/after prompt examples
  - [ ] 7.1.3 Explain how to enable/disable
  - [ ] 7.1.4 Add troubleshooting tips

---

## Optional Enhancements (Only if needed)

### Task 8: Emotional Arc Visualization*
- [ ]* 8.1 Add simple emotional tone detection
  - [ ]* 8.1.1 Detect if scene is tense, calm, dramatic, or action-packed
  - [ ]* 8.1.2 Adjust camera suggestions: tense = close-up, calm = wide shot
  - [ ]* 8.1.3 Add to prompt: "Camera: [close-up/wide shot] to match [emotional tone]"

### Task 9: Better Transition Hints*
- [ ]* 9.1 Add smarter transition detection
  - [ ]* 9.1.1 Detect time jumps (hours/days later)
  - [ ]* 9.1.2 Detect flashbacks or parallel scenes
  - [ ]* 9.1.3 Add appropriate transition hints to prompts

---

## Success Criteria

### Must Have (Phase 1-3)
- ✅ Prompts include context from previous scene
- ✅ Character descriptions stay consistent
- ✅ Simple location/transition hints added
- ✅ Works with existing pipeline (no breaking changes)
- ✅ Enhanced prompts under 950 characters
- ✅ Scenes feel more connected when watching video

### Nice to Have (Optional)
- Emotional tone affects camera suggestions
- Smart transition detection
- Visual examples in documentation

---

## Implementation Notes

**Keep It Simple:**
- Don't build complex graph structures - just track previous scene
- Don't over-analyze emotions - just detect basic tone from keywords
- Don't create new file formats - work with existing prompts.yaml
- Don't add dependencies - use existing libraries (yaml, re)

**Focus on Impact:**
- The goal is visual continuity, not perfect story analysis
- Simple context injection will make a huge difference
- Character consistency is more important than complex transitions
- Test early and often with real examples

**Integration:**
- Should work as a simple post-processing step
- Existing pipeline shouldn't need major changes
- Should be easy to enable/disable for testing
- Backward compatible with old prompts

---

## Estimated Effort

- **Phase 1**: 4-6 hours (core story context)
- **Phase 2**: 2-3 hours (character consistency)
- **Phase 3**: 2-3 hours (testing and docs)
- **Total MVP**: 8-12 hours

Optional enhancements: 2-4 hours each if needed
