# Design Document: Cinematic Storytelling System

## Overview

The Cinematic Storytelling System transforms disconnected scene generation into a cohesive visual narrative with movie-like flow. It analyzes story structure, maintains visual continuity, and generates prompts that create seamless transitions between scenes while preserving character consistency and emotional progression.

### Problem Statement

Current video generation creates isolated scenes without:
- Visual continuity between consecutive scenes
- Story progression reflected in cinematography
- Character consistency across the narrative
- Emotional arc visualization
- Cinematic transitions and pacing

### Solution Approach

A multi-stage pipeline that:
1. **Analyzes** the script for story structure, emotional beats, and character arcs
2. **Plans** visual continuity with scene relationships and transitions
3. **Generates** enhanced prompts with cinematic context
4. **Validates** continuity constraints before video generation

---

## High-Level Design

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Story Analysis Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Script       │  │ Emotional    │  │ Character    │      │
│  │ Parser       │  │ Arc Analyzer │  │ Arc Tracker  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                 Scene Continuity Engine                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Scene Graph  │  │ Transition   │  │ Camera       │      │
│  │ Builder      │  │ Planner      │  │ Flow Manager │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Cinematic Prompt Generator                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Context      │  │ Visual       │  │ Continuity   │      │
│  │ Enricher     │  │ Composer     │  │ Validator    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Video Generation Orchestrator                   │
│                  (Existing Grok2API)                         │
└─────────────────────────────────────────────────────────────┘
```

### Component Descriptions

#### 1. Story Analysis Layer

**Script Parser**
- Extracts narrative beats from timestamped script
- Identifies scene boundaries and dialogue segments
- Maps narration timing to visual moments

**Emotional Arc Analyzer**
- Detects emotional intensity across the story
- Identifies dramatic peaks and valleys
- Tags scenes with emotional states (tension, relief, climax, resolution)

**Character Arc Tracker**
- Tracks character presence and state changes
- Identifies character relationships and interactions
- Maintains character journey through the narrative

#### 2. Scene Continuity Engine

**Scene Graph Builder**
- Creates directed graph of scene relationships
- Defines predecessor/successor connections
- Identifies parallel storylines and flashbacks

**Transition Planner**
- Determines transition types (cut, fade, match-cut, etc.)
- Plans visual bridges between scenes
- Ensures spatial and temporal coherence

**Camera Flow Manager**
- Plans camera movements across scenes
- Maintains consistent perspective and framing
- Creates visual rhythm through shot composition

#### 3. Cinematic Prompt Generator

**Context Enricher**
- Injects previous scene context into prompts
- Adds character state and positioning information
- Includes emotional tone and pacing cues

**Visual Composer**
- Generates composition guidelines (rule of thirds, leading lines)
- Plans lighting and color palette progression
- Defines depth and spatial relationships

**Continuity Validator**
- Checks character appearance consistency
- Validates spatial relationships between scenes
- Ensures logical visual progression

---

## Low-Level Design

### Data Models

#### Scene Metadata
```python
@dataclass
class SceneMetadata:
    scene_number: int
    timestamp_start: float
    timestamp_end: float
    duration: float
    narration_text: str
    
    # Story context
    emotional_intensity: float  # 0.0 to 1.0
    emotional_state: EmotionalState  # enum
    story_beat: StoryBeat  # enum (setup, conflict, climax, resolution)
    
    # Visual context
    characters_present: List[str]
    location: str
    time_of_day: TimeOfDay  # enum
    
    # Cinematic context
    camera_angle: CameraAngle  # enum
    shot_type: ShotType  # enum (wide, medium, close-up)
    movement_type: MovementType  # enum (static, pan, zoom, dolly)
    
    # Continuity
    predecessor_scene: Optional[int]
    successor_scene: Optional[int]
    transition_type: TransitionType  # enum
```

#### Character State
```python
@dataclass
class CharacterState:
    name: str
    scene_number: int
    
    # Visual attributes
    position: Position  # (x, y, z) or descriptive
    facing_direction: Direction  # enum
    emotional_expression: Expression  # enum
    action: str  # current action description
    
    # Appearance
    clothing: str
    accessories: List[str]
    visual_anchor: str  # consistent description
    
    # Continuity tracking
    last_seen_scene: int
    state_changes: List[StateChange]
```

#### Transition Specification
```python
@dataclass
class TransitionSpec:
    from_scene: int
    to_scene: int
    transition_type: TransitionType
    
    # Visual continuity
    match_elements: List[str]  # elements to maintain across transition
    camera_continuity: CameraContinuity
    
    # Timing
    transition_duration: float  # seconds
    overlap_frames: int
    
    # Prompt modifications
    exit_prompt_suffix: str  # added to scene N
    entry_prompt_prefix: str  # added to scene N+1
```

### Core Algorithms

#### Algorithm 1: Scene Graph Construction

```python
def build_scene_graph(scenes: List[Scene], script: Script) -> SceneGraph:
    """
    Constructs a directed graph of scene relationships with continuity metadata.
    
    Preconditions:
        - scenes is non-empty and ordered by scene_number
        - script contains timestamped narration matching scenes
    
    Postconditions:
        - Returns SceneGraph with all scenes as nodes
        - Each scene has edges to predecessor/successor
        - Transition types are assigned based on narrative analysis
    """
    graph = SceneGraph()
    
    # Add all scenes as nodes
    for scene in scenes:
        metadata = extract_scene_metadata(scene, script)
        graph.add_node(scene.scene_number, metadata)
    
    # Build edges with transition analysis
    for i in range(len(scenes) - 1):
        current = scenes[i]
        next_scene = scenes[i + 1]
        
        # Analyze transition requirements
        transition = analyze_transition(
            current_metadata=graph.get_node(current.scene_number),
            next_metadata=graph.get_node(next_scene.scene_number),
            script=script
        )
        
        graph.add_edge(
            current.scene_number,
            next_scene.scene_number,
            transition
        )
    
    return graph

def analyze_transition(
    current_metadata: SceneMetadata,
    next_metadata: SceneMetadata,
    script: Script
) -> TransitionSpec:
    """
    Determines optimal transition type based on narrative context.
    
    Invariants:
        - Emotional jumps > 0.5 intensity → fade transition
        - Location changes → cut transition
        - Character continuity → match-cut transition
        - Time jumps → dissolve transition
    """
    transition_type = TransitionType.CUT  # default
    
    # Check emotional continuity
    emotional_delta = abs(
        next_metadata.emotional_intensity - 
        current_metadata.emotional_intensity
    )
    
    if emotional_delta > 0.5:
        transition_type = TransitionType.FADE
    
    # Check spatial continuity
    elif current_metadata.location != next_metadata.location:
        transition_type = TransitionType.CUT
    
    # Check character continuity
    elif has_character_continuity(current_metadata, next_metadata):
        transition_type = TransitionType.MATCH_CUT
    
    # Check temporal continuity
    elif has_time_jump(current_metadata, next_metadata):
        transition_type = TransitionType.DISSOLVE
    
    return TransitionSpec(
        from_scene=current_metadata.scene_number,
        to_scene=next_metadata.scene_number,
        transition_type=transition_type,
        match_elements=find_match_elements(current_metadata, next_metadata),
        camera_continuity=plan_camera_continuity(
            current_metadata, next_metadata
        )
    )
```

#### Algorithm 2: Character Consistency Tracking

```python
def track_character_consistency(
    scenes: List[Scene],
    scene_graph: SceneGraph
) -> Dict[str, List[CharacterState]]:
    """
    Maintains character state across all scenes for visual consistency.
    
    Preconditions:
        - scenes contain character_profile with appearance_anchor
        - scene_graph has valid predecessor/successor relationships
    
    Postconditions:
        - Returns character state history for all characters
        - Each state transition is validated for continuity
        - Appearance anchors are consistent across scenes
    
    Loop Invariant:
        For each scene i processed:
        - All characters in scene i have state entries
        - State changes from scene i-1 to i are documented
        - Visual anchors remain consistent unless explicitly changed
    """
    character_states: Dict[str, List[CharacterState]] = {}
    
    for scene in scenes:
        metadata = scene_graph.get_node(scene.scene_number)
        
        for character_name in metadata.characters_present:
            if character_name not in character_states:
                character_states[character_name] = []
            
            # Get previous state if exists
            prev_state = get_last_state(character_states[character_name])
            
            # Extract current state from scene
            current_state = extract_character_state(
                scene, character_name, metadata
            )
            
            # Validate continuity
            if prev_state:
                validate_state_transition(
                    prev_state, current_state, metadata
                )
            
            character_states[character_name].append(current_state)
    
    return character_states

def validate_state_transition(
    prev: CharacterState,
    current: CharacterState,
    metadata: SceneMetadata
) -> None:
    """
    Ensures character state changes are narratively justified.
    
    Raises:
        ContinuityError: If state change violates continuity rules
    """
    # Check appearance consistency
    if prev.visual_anchor != current.visual_anchor:
        if not has_costume_change_justification(prev, current, metadata):
            raise ContinuityError(
                f"Character {current.name} appearance changed without "
                f"narrative justification between scenes "
                f"{prev.scene_number} and {current.scene_number}"
            )
    
    # Check spatial continuity
    if prev.position and current.position:
        distance = calculate_position_distance(prev.position, current.position)
        time_gap = metadata.timestamp_start - prev.scene_number * 6.0
        
        if distance > max_travel_distance(time_gap):
            raise ContinuityError(
                f"Character {current.name} moved too far "
                f"({distance}) in {time_gap}s"
            )
```

#### Algorithm 3: Cinematic Prompt Enhancement

```python
def enhance_prompt_with_continuity(
    scene: Scene,
    scene_graph: SceneGraph,
    character_states: Dict[str, List[CharacterState]],
    base_prompt: str
) -> str:
    """
    Enriches base prompt with cinematic context and continuity information.
    
    Preconditions:
        - scene exists in scene_graph
        - character_states contains all characters in scene
        - base_prompt is non-empty
    
    Postconditions:
        - Returns enhanced prompt with:
          * Previous scene visual context
          * Character positioning and state
          * Camera movement continuity
          * Transition cues
        - Prompt length ≤ 950 characters (API limit)
    """
    metadata = scene_graph.get_node(scene.scene_number)
    enhanced_parts = []
    
    # 1. Add style and visual foundation
    enhanced_parts.append(base_prompt)
    
    # 2. Add previous scene context for continuity
    if metadata.predecessor_scene:
        prev_context = generate_predecessor_context(
            scene_graph, metadata.predecessor_scene
        )
        enhanced_parts.append(f"CONTINUING FROM: {prev_context}")
    
    # 3. Add character positioning and state
    for char_name in metadata.characters_present:
        char_state = get_character_state_for_scene(
            character_states, char_name, scene.scene_number
        )
        char_context = format_character_context(char_state)
        enhanced_parts.append(char_context)
    
    # 4. Add camera continuity
    camera_context = generate_camera_context(
        scene_graph, metadata, scene.scene_number
    )
    enhanced_parts.append(camera_context)
    
    # 5. Add transition cues
    transition = scene_graph.get_edge(
        metadata.predecessor_scene, scene.scene_number
    )
    if transition:
        transition_cue = format_transition_cue(transition)
        enhanced_parts.append(transition_cue)
    
    # 6. Combine and truncate if needed
    enhanced_prompt = " ".join(enhanced_parts)
    
    if len(enhanced_prompt) > 950:
        enhanced_prompt = truncate_prompt_intelligently(
            enhanced_prompt, max_length=950
        )
    
    return enhanced_prompt

def generate_predecessor_context(
    scene_graph: SceneGraph,
    prev_scene_num: int
) -> str:
    """
    Generates context string describing the previous scene's ending state.
    
    Returns:
        Concise description of visual elements to maintain continuity
    """
    prev_metadata = scene_graph.get_node(prev_scene_num)
    
    context_elements = []
    
    # Location continuity
    if prev_metadata.location:
        context_elements.append(f"location: {prev_metadata.location}")
    
    # Character positions
    if prev_metadata.characters_present:
        char_positions = ", ".join(prev_metadata.characters_present)
        context_elements.append(f"characters: {char_positions}")
    
    # Camera state
    if prev_metadata.camera_angle:
        context_elements.append(f"camera: {prev_metadata.camera_angle.value}")
    
    return "; ".join(context_elements)
```

#### Algorithm 4: Emotional Arc Visualization

```python
def map_emotional_arc_to_visuals(
    scenes: List[Scene],
    script: Script
) -> List[VisualGuideline]:
    """
    Translates emotional story beats into visual composition guidelines.
    
    Preconditions:
        - scenes are ordered chronologically
        - script contains emotional markers or can be analyzed
    
    Postconditions:
        - Returns visual guidelines for each scene
        - Guidelines reflect emotional progression
        - Color, lighting, and composition vary with emotional arc
    
    Emotional Mapping Rules:
        - High tension → tight framing, dark colors, sharp angles
        - Relief → wider shots, warm colors, balanced composition
        - Climax → dynamic camera, high contrast, dramatic lighting
        - Resolution → static camera, soft colors, centered composition
    """
    emotional_curve = analyze_emotional_curve(script)
    guidelines = []
    
    for i, scene in enumerate(scenes):
        emotional_intensity = emotional_curve[i]
        emotional_state = classify_emotional_state(
            emotional_intensity, i, len(scenes)
        )
        
        guideline = VisualGuideline(
            scene_number=scene.scene_number,
            emotional_intensity=emotional_intensity,
            emotional_state=emotional_state
        )
        
        # Map emotion to visual parameters
        if emotional_state == EmotionalState.TENSION:
            guideline.shot_type = ShotType.CLOSE_UP
            guideline.color_palette = ColorPalette.DARK_DESATURATED
            guideline.camera_angle = CameraAngle.LOW_ANGLE
            guideline.lighting = LightingStyle.HARSH_SHADOWS
        
        elif emotional_state == EmotionalState.RELIEF:
            guideline.shot_type = ShotType.MEDIUM
            guideline.color_palette = ColorPalette.WARM_SATURATED
            guideline.camera_angle = CameraAngle.EYE_LEVEL
            guideline.lighting = LightingStyle.SOFT_NATURAL
        
        elif emotional_state == EmotionalState.CLIMAX:
            guideline.shot_type = ShotType.DYNAMIC
            guideline.color_palette = ColorPalette.HIGH_CONTRAST
            guideline.camera_angle = CameraAngle.DUTCH_ANGLE
            guideline.lighting = LightingStyle.DRAMATIC
        
        elif emotional_state == EmotionalState.RESOLUTION:
            guideline.shot_type = ShotType.WIDE
            guideline.color_palette = ColorPalette.SOFT_PASTEL
            guideline.camera_angle = CameraAngle.EYE_LEVEL
            guideline.lighting = LightingStyle.EVEN_AMBIENT
        
        guidelines.append(guideline)
    
    return guidelines
```

---

## Integration Points

### 1. Input Integration
- **Existing**: `prompts.yaml` with scene list
- **New**: Enhanced with scene_graph, character_states, transitions
- **Modification**: Add metadata fields to each scene entry

### 2. Prompt Generation Integration
- **Existing**: `utils/multimodal_orchestrator.py` generates base prompts
- **New**: Post-process prompts through `enhance_prompt_with_continuity()`
- **Modification**: Add continuity enhancement step before writing prompts.yaml

### 3. Video Generation Integration
- **Existing**: `utils/generate_videos.py` reads prompts and generates videos
- **New**: No changes needed - enhanced prompts work with existing API
- **Modification**: None required

### 4. Configuration Integration
- **New File**: `cinematic_config.yaml` for continuity rules and thresholds
- **Location**: Project root or `.kiro/` directory
- **Contents**: Transition rules, character consistency thresholds, emotional mapping

---

## Testing Strategy

### Property-Based Testing

#### Property 1: Scene Graph Connectivity
```python
@given(scenes=st.lists(st.builds(Scene), min_size=2))
def test_scene_graph_connectivity(scenes):
    """Every scene except the last has a successor."""
    graph = build_scene_graph(scenes, mock_script)
    
    for i in range(len(scenes) - 1):
        assert graph.has_edge(scenes[i].scene_number, scenes[i+1].scene_number)
```

#### Property 2: Character Appearance Consistency
```python
@given(
    scenes=st.lists(st.builds(Scene), min_size=3),
    character=st.text(min_size=1)
)
def test_character_appearance_consistency(scenes, character):
    """Character visual anchor remains consistent unless explicitly changed."""
    states = track_character_consistency(scenes, scene_graph)
    
    if character in states:
        anchors = [s.visual_anchor for s in states[character]]
        # Either all same, or changes are justified
        assert len(set(anchors)) == 1 or has_justified_changes(states[character])
```

#### Property 3: Transition Coherence
```python
@given(scene_pairs=st.lists(st.tuples(st.builds(Scene), st.builds(Scene))))
def test_transition_coherence(scene_pairs):
    """Transitions between scenes follow narrative logic."""
    for scene1, scene2 in scene_pairs:
        transition = analyze_transition(
            scene1.metadata, scene2.metadata, mock_script
        )
        
        # Emotional jumps require fade/dissolve
        if abs(scene1.emotional_intensity - scene2.emotional_intensity) > 0.5:
            assert transition.transition_type in [
                TransitionType.FADE, TransitionType.DISSOLVE
            ]
```

#### Property 4: Prompt Length Constraint
```python
@given(
    scene=st.builds(Scene),
    base_prompt=st.text(min_size=100, max_size=800)
)
def test_enhanced_prompt_length(scene, base_prompt):
    """Enhanced prompts never exceed API limit."""
    enhanced = enhance_prompt_with_continuity(
        scene, scene_graph, character_states, base_prompt
    )
    
    assert len(enhanced) <= 950
```

---

## Performance Considerations

### Computational Complexity

- **Scene Graph Construction**: O(n) where n = number of scenes
- **Character Tracking**: O(n × c) where c = number of characters
- **Prompt Enhancement**: O(n) with constant-time lookups
- **Overall Pipeline**: O(n × c) - linear in scenes and characters

### Memory Requirements

- Scene graph: ~1KB per scene
- Character states: ~500 bytes per character per scene
- For typical video (30 scenes, 5 characters): ~165KB total

### Optimization Strategies

1. **Lazy Loading**: Load scene metadata on-demand
2. **Caching**: Cache transition analysis results
3. **Parallel Processing**: Generate enhanced prompts in parallel
4. **Incremental Updates**: Only reprocess changed scenes

---

## Future Enhancements

### Phase 2 Features

1. **Multi-timeline Support**: Handle flashbacks and parallel storylines
2. **Dynamic Character Relationships**: Track and visualize character interactions
3. **Location Memory**: Maintain consistent location appearances across scenes
4. **Style Evolution**: Gradually shift visual style with story progression

### Phase 3 Features

1. **AI-Assisted Storyboarding**: Generate visual storyboards from script
2. **Automatic Shot Selection**: ML-based optimal shot type selection
3. **Emotion Recognition**: Analyze narration audio for emotional cues
4. **Interactive Editing**: UI for manual continuity adjustments

---

## Appendix: Enums and Constants

```python
class EmotionalState(Enum):
    NEUTRAL = "neutral"
    TENSION = "tension"
    RELIEF = "relief"
    CLIMAX = "climax"
    RESOLUTION = "resolution"

class StoryBeat(Enum):
    SETUP = "setup"
    INCITING_INCIDENT = "inciting_incident"
    RISING_ACTION = "rising_action"
    CLIMAX = "climax"
    FALLING_ACTION = "falling_action"
    RESOLUTION = "resolution"

class TransitionType(Enum):
    CUT = "cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    MATCH_CUT = "match_cut"
    WIPE = "wipe"

class CameraAngle(Enum):
    EYE_LEVEL = "eye_level"
    LOW_ANGLE = "low_angle"
    HIGH_ANGLE = "high_angle"
    DUTCH_ANGLE = "dutch_angle"
    BIRDS_EYE = "birds_eye"

class ShotType(Enum):
    WIDE = "wide"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"
    EXTREME_CLOSE_UP = "extreme_close_up"
    DYNAMIC = "dynamic"

# Continuity thresholds
MAX_EMOTIONAL_JUMP = 0.5  # intensity units
MAX_SPATIAL_JUMP = 100.0  # arbitrary units
MIN_TRANSITION_DURATION = 0.5  # seconds
```
