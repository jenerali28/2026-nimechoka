# Requirements Document: Story Flow Enhancement

## Overview

A simple system to make video scenes flow together like a movie instead of looking random. The system adds story context to prompts so each scene connects to the previous one, maintaining character consistency and visual continuity.

**Core Goal**: Enhance existing prompts with previous scene context to create visual storytelling flow.

---

## Functional Requirements


### FR1: Story Context Tracking

**FR1.1: Previous Scene Context**
- The system shall read the script to understand what happened in each scene
- The system shall track location, characters present, and main action for each scene
- The system shall store simple context: "Previous scene: [location], [characters], [action]"

**FR1.2: Basic Emotional Tone**
- The system shall detect basic emotional tone from script keywords (tense, calm, dramatic, action)
- The system shall identify major emotional shifts between scenes
- The system shall use simple keyword matching (no complex NLP required)

### FR2: Prompt Enhancement

**FR2.1: Context Injection**
- The system shall read existing prompts.yaml file
- The system shall add previous scene context to each prompt
- The system shall add transition hints: "Continuing from [previous context]..."
- The system shall ensure enhanced prompts stay under 950 characters

**FR2.2: Character Consistency**
- The system shall extract character descriptions from prompts.yaml character_profile
- The system shall inject consistent character appearance when they appear in scenes
- The system shall use the appearance_anchor field for each character
- Example: "The Protagonist (thin black stick figure, long dark hair, olive face) continues..."

**FR2.3: Location Continuity**
- The system shall detect location changes between scenes
- The system shall add "Scene shifts to [new location]" when location changes
- The system shall add "Still in [location]" when location stays the same
- The system shall keep location hints simple (1-2 sentences max)

### FR3: Integration

**FR3.1: Pipeline Integration**
- The system shall work as a post-processing step after base prompt generation
- The system shall integrate with existing multimodal_orchestrator.py
- The system shall not break existing pipeline functionality
- The system shall be easy to enable/disable with a simple flag

**FR3.2: File Handling**
- The system shall read existing prompts.yaml without modification
- The system shall write enhanced prompts back to prompts.yaml
- The system shall preserve all existing prompt structure and metadata
- The system shall work with current file formats (no new formats)

---

## Non-Functional Requirements

### NFR1: Simplicity

**NFR1.1: No Complex Dependencies**
- The system shall use only existing libraries (yaml, re, pathlib)
- The system shall not require new external dependencies
- The system shall not use complex NLP or ML libraries
- The system shall use simple string manipulation and pattern matching

**NFR1.2: Minimal Code**
- The system shall be implemented in 2-3 simple Python modules
- The system shall avoid complex data structures (use dicts and lists)
- The system shall not build graph structures or state machines
- The system shall keep functions small and focused

### NFR2: Performance

**NFR2.1: Fast Processing**
- The system shall process 30 scenes in under 5 seconds
- The system shall add minimal overhead to existing pipeline
- The system shall not require caching or optimization
- The system shall use simple linear processing

**NFR2.2: Low Memory**
- The system shall use minimal memory (< 50KB for 30 scenes)
- The system shall not store complex state or history
- The system shall process scenes sequentially without buffering

### NFR3: Reliability

**NFR3.1: Error Handling**
- The system shall handle missing script files gracefully
- The system shall handle malformed prompts.yaml gracefully
- The system shall continue processing if one scene fails
- The system shall log warnings but not crash the pipeline

**NFR3.2: Backward Compatibility**
- The system shall work with existing prompts.yaml format
- The system shall not require changes to other pipeline components
- The system shall be optional (pipeline works without it)
- The system shall preserve all existing prompt fields

### NFR4: Maintainability

**NFR4.1: Simple Code**
- The system shall use clear, readable Python code
- The system shall include basic docstrings
- The system shall avoid clever tricks or complex algorithms
- The system shall be easy to understand and modify

**NFR4.2: Easy Testing**
- The system shall be testable with simple unit tests
- The system shall not require complex test fixtures
- The system shall work with real example data for testing
- The system shall include basic integration test

---

## User Stories

### US1: As a content creator, I want scenes to connect visually
**Acceptance Criteria:**
- Each scene prompt includes context from previous scene
- Scenes feel connected when watching the video
- No jarring jumps between scenes
- Characters look the same across scenes

### US2: As a content creator, I want consistent character appearance
**Acceptance Criteria:**
- Character descriptions stay the same across scenes
- Clothing and appearance don't randomly change
- Character names and descriptions are injected consistently

### US3: As a developer, I want easy integration
**Acceptance Criteria:**
- System works with existing pipeline
- Can be enabled/disabled with one flag
- No breaking changes to existing code
- Works with current file formats

### US4: As a developer, I want simple code
**Acceptance Criteria:**
- Code is easy to read and understand
- No complex algorithms or data structures
- Uses only existing dependencies
- Can be modified without breaking things

---

## Success Metrics

### Quality Metrics
- Scenes feel more connected (subjective improvement)
- Character descriptions are consistent (100%)
- Location transitions are clear
- Enhanced prompts under 950 characters (100%)

### Performance Metrics
- Processing time: < 5 seconds for 30 scenes
- Memory usage: < 50KB
- No noticeable slowdown in pipeline
- Works on first try with existing data

### Adoption Metrics
- Integration time: < 1 hour
- Learning curve: < 15 minutes
- No bugs in basic functionality
- Easy to enable/disable for testing

---

## Constraints

### Technical Constraints
- Must work with existing prompts.yaml format
- Must keep prompts under 950 characters
- Must use only existing Python libraries
- Must not break existing pipeline

### Simplicity Constraints
- No complex data structures
- No graph algorithms
- No ML or NLP libraries
- No new file formats

### Integration Constraints
- Must be optional (can be disabled)
- Must work as post-processing step
- Must not require changes to other components
- Must preserve backward compatibility

---

## Out of Scope

The following are explicitly **NOT** part of this simple system:

- ❌ Complex emotional arc analysis
- ❌ Scene graph structures
- ❌ Advanced transition detection
- ❌ Camera angle planning
- ❌ Spatial continuity validation
- ❌ Property-based testing
- ❌ Configuration files
- ❌ Visualization tools
- ❌ ML-based analysis
- ❌ Complex state tracking

These may be added later if needed, but the MVP focuses on simple context injection.

---

## Dependencies

### Input Dependencies
- Script file (english_script.txt or spanish_script.txt)
- Existing prompts.yaml with scenes and character_profile
- Scene timing information (optional, from script timestamps)

### Output Dependencies
- Enhanced prompts.yaml (same format, enhanced content)

### External Dependencies
- Python 3.10+ (already required)
- PyYAML (already installed)
- Standard library: re, pathlib, typing

---

## Implementation Approach

### Simple 3-Step Process

**Step 1: Read Context**
```python
# For each scene, extract:
context = {
    'location': 'desert',
    'characters': ['Protagonist'],
    'action': 'standing alone',
    'tone': 'calm'
}
```

**Step 2: Enhance Prompt**
```python
# Add context to prompt:
enhanced = f"Continuing from {prev_location} with {prev_characters}. {original_prompt}"
```

**Step 3: Write Back**
```python
# Write enhanced prompts to prompts.yaml
# Keep all existing structure intact
```

### Example Enhancement

**Before:**
```
"A desert landscape. The Protagonist stands alone."
```

**After:**
```
"Continuing from the mud-brick hut. The Protagonist (thin black stick figure, 
long dark hair, olive face, white dress) now stands in a desert landscape."
```

---

## Risks and Mitigations

### Risk 1: Prompt Length Overflow
**Impact**: Medium - Prompts exceed 950 characters
**Probability**: Low
**Mitigation**: Simple truncation, prioritize character consistency

### Risk 2: Context Not Helpful
**Impact**: Low - Added context doesn't improve flow
**Probability**: Low  
**Mitigation**: Easy to disable, test with real examples first

### Risk 3: Integration Issues
**Impact**: Medium - Breaks existing pipeline
**Probability**: Very Low
**Mitigation**: Post-processing step, optional flag, thorough testing

---

## Future Enhancements (Maybe Later)

If the simple version works well, we could add:

1. **Better emotional tone detection** - Use more keywords, detect intensity
2. **Smarter transitions** - Detect time jumps, flashbacks
3. **Camera suggestions** - Add camera hints based on tone
4. **Configuration** - Allow customization of context format

But these are **NOT** required for MVP. Keep it simple first.

---

## Glossary

**Story Context**: Simple information about previous scene (location, characters, action)

**Prompt Enhancement**: Adding context to existing prompts without changing structure

**Character Consistency**: Using same character description across all scenes

**Location Continuity**: Noting when location changes or stays the same

**Emotional Tone**: Basic mood of scene (tense, calm, dramatic, action)

**Appearance Anchor**: Consistent character description from character_profile

**Context Injection**: Adding previous scene context to current scene prompt
