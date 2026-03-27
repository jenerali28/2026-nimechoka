import os
import ffmpeg
import logging
import subprocess
import shutil
import platform
import json
import re
from typing import List, Dict, Tuple
import tempfile
import whisper
from pathlib import Path
import uuid
import glob

# Set the default local storage directory
STORAGE_PATH = "./tmp/"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_available_fonts():
    """Scan the fonts folder for available font files"""
    fonts_dir = "fonts"
    if not os.path.exists(fonts_dir):
        logger.warning(f"Fonts directory '{fonts_dir}' not found")
        return []
    
    # Look for common font file extensions
    font_extensions = ['*.ttf', '*.otf', '*.woff', '*.woff2']
    available_fonts = []
    
    for ext in font_extensions:
        font_files = glob.glob(os.path.join(fonts_dir, ext))
        available_fonts.extend(font_files)
    
    if available_fonts:
        logger.info(f"Found {len(available_fonts)} font files: {[os.path.basename(f) for f in available_fonts]}")
    else:
        logger.warning("No font files found in fonts directory")
    
    return available_fonts

def select_best_font():
    """Select the best available font from the fonts folder"""
    available_fonts = get_available_fonts()
    
    if not available_fonts:
        logger.warning("No custom fonts available, using system fallback")
        return 'Arial Bold'
    
    # Use relative paths for better portability
    font_paths = [os.path.relpath(font) for font in available_fonts]
    
    # Prefer fonts with certain keywords (in order of preference)
    preferred_keywords = ['bold', 'semibold', 'medium', 'regular']
    
    for keyword in preferred_keywords:
        for font_path in font_paths:
            font_name = os.path.basename(font_path).lower()
            if keyword in font_name:
                logger.info(f"Selected font: {font_path} (matched keyword: {keyword})")
                return font_path
    
    # If no preferred font found, use the first available
    selected_font = font_paths[0]
    logger.info(f"Selected first available font: {selected_font}")
    return selected_font

def ensure_temp_directory():
    """Ensure the temporary directory exists"""
    if not os.path.exists(STORAGE_PATH):
        os.makedirs(STORAGE_PATH)
        logger.info(f"Created temporary directory: {STORAGE_PATH}")

class ImprovedSentenceHighlightGenerator:
    """Improved sentence-based caption generator with simpler segment display"""
    
    def __init__(self, max_chars_per_line=40): # Reduced for shorter segments
        self.max_chars_per_line = max_chars_per_line
        # Common sentence endings
        self.sentence_endings = {'.', '!', '?', '...'}
        # Words that typically don't end sentences even with periods
        self.abbreviations = {'mr', 'mrs', 'dr', 'prof', 'vs', 'etc', 'inc', 'corp', 'ltd'}
    
    def format_time_ass(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.CC)"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"
    
    def sanitize_text(self, text: str) -> str:
        """Sanitize text for ASS format - escape special characters"""
        # Remove or escape problematic characters
        text = text.replace('\\', '\\\\')  # Escape backslashes
        text = text.replace('{', '\\{')    # Escape curly braces
        text = text.replace('}', '\\}')
        text = re.sub(r'[^\x20-\x7E]', '', text)  # Remove non-ASCII characters
        return text.strip()
    
    def is_sentence_end(self, word: str, next_word: str = None) -> bool:
        """Determine if a word ends a sentence"""
        word_clean = word.lower().strip('.,!?')
        
        # Check if word ends with sentence punctuation
        if any(word.endswith(ending) for ending in self.sentence_endings):
            # Don't break on common abbreviations unless next word is capitalized
            if word_clean in self.abbreviations:
                if next_word and next_word[0].isupper():
                    return True
                return False
            return True
        return False
    
    def group_words_into_sentences(self, word_timings: List[Dict]) -> List[List[Dict]]:
        """Group words into complete sentences"""
        if not word_timings:
            return []
        
        sentences = []
        current_sentence = []
        
        for i, word_info in enumerate(word_timings):
            word = self.sanitize_text(word_info.get('word', ''))
            if not word:  # Skip empty words
                continue
            
            # Add word to current sentence
            word_info_copy = word_info.copy()
            word_info_copy['word'] = word
            current_sentence.append(word_info_copy)
            
            # Check if this word ends the sentence
            next_word = None
            if i + 1 < len(word_timings):
                next_word = word_timings[i + 1].get('word', '')
            
            if self.is_sentence_end(word, next_word):
                sentences.append(current_sentence)
                current_sentence = []
            # Also break if sentence gets too long (fallback)
            elif len(' '.join([w['word'] for w in current_sentence])) > self.max_chars_per_line:
                sentences.append(current_sentence)
                current_sentence = []
        
        # Add remaining words as final sentence
        if current_sentence:
            sentences.append(current_sentence)
        
        return sentences
    
    def split_long_sentence(self, words: List[Dict]) -> List[List[Dict]]:
        """Split a long sentence into multiple lines at natural break points"""
        if len(' '.join([w['word'] for w in words])) <= self.max_chars_per_line:
            return [words]
        
        lines = []
        current_line = []
        current_length = 0
        
        # Break points (in order of preference)
        break_words = {'and', 'or', 'but', 'because', 'since', 'while', 'when', 'where', 'who', 'which', 'that'}
        comma_positions = []
        break_positions = []
        
        # Find potential break points
        for i, word_info in enumerate(words):
            word = word_info['word']
            current_line.append(word_info)
            current_length += len(word) + 1
            
            # Mark comma positions
            if word.endswith(','):
                comma_positions.append(i)
            
            # Mark natural break word positions
            if word.lower().strip('.,!?') in break_words:
                break_positions.append(i)
            
            # If line is getting long, look for a break point
            if current_length > self.max_chars_per_line * 0.7:  # 70% of max length
                break_point = None
                
                # Find the best break point working backwards
                for pos in reversed(comma_positions + break_positions):
                    if pos < len(current_line) - 1:  # Don't break on the last word
                        break_point = pos
                        break
                
                # If no good break point, just break at current position
                if break_point is None and len(current_line) > 1:
                    break_point = len(current_line) - 2
                
                if break_point is not None:
                    # Split at break point
                    lines.append(current_line[:break_point + 1])
                    current_line = current_line[break_point + 1:]
                    current_length = sum(len(w['word']) + 1 for w in current_line)
                    comma_positions = [p - break_point - 1 for p in comma_positions if p > break_point]
                    break_positions = [p - break_point - 1 for p in break_positions if p > break_point]
        
        # Add remaining words
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def create_sentence_segment_line(self, words: List[Dict]) -> str:
        """Create an ASS dialogue line for a segment without highlighting"""
        if not words:
            return ""

        start_time = words[0]['start']
        end_time = words[-1]['end']
        
        # Ensure valid timing
        if end_time <= start_time:
            end_time = start_time + 0.5  # Minimum duration
        
        # Build the complete text
        full_text = " ".join([w['word'] for w in words])
        
        start_ass = self.format_time_ass(start_time)
        end_ass = self.format_time_ass(end_time)
        
        return f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{full_text}"
    
    def generate_ass_header(self, options: Dict = None) -> str:
        """Generate ASS file header with proper styling for single-word captions"""
        if options is None:
            options = {}
        
        font_name = options.get('font_name', 'Arial Bold')
        font_size = options.get('font_size', 16)
        primary_color = options.get('primary_color', '&H00FFFFFF')  # White
        outline_color = options.get('outline_color', '&H00000000')  # Black
        back_color = options.get('back_color', '&H80000000')
        outline = options.get('outline', 2)
        shadow = options.get('shadow', 1)
        alignment = options.get('alignment', 2)  # Bottom center
        margin_v = options.get('margin_v', 35)
        
        header = (
            "[Script Info]\n"
            "Title: Word-by-Word Captions\n"
            "ScriptType: v4.00+\n"
            "Collisions: Normal\n"
            "PlayDepth: 0\n"
            "Timer: 100.0000\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font_name},{font_size},{primary_color},{primary_color},"
            f"{outline_color},{back_color},-1,0,0,0,100,100,0,0,1,{outline},{shadow},"
            f"{alignment},10,10,{margin_v},1\n"
            "\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        return header

    def generate_word_by_word_ass(self, word_timings: List[Dict],
                                  output_path: str, options: Dict = None) -> str:
        """Generate ASS file showing ONE word at a time at the bottom of the screen."""
        if not word_timings:
            raise ValueError("No word timings provided")
        
        # Filter valid timings
        valid = [
            w for w in word_timings
            if (isinstance(w, dict) and 'word' in w and 'start' in w and 'end' in w
                and isinstance(w['start'], (int, float))
                and isinstance(w['end'], (int, float))
                and w['end'] > w['start'])
        ]
        if not valid:
            raise ValueError("No valid word timings found")
        
        logger.info(f"Generating word-by-word captions for {len(valid)} words")
        
        ass_content = self.generate_ass_header(options)
        dialogue_lines = []
        last_end = 0.0
        
        for w in valid:
            word = self.sanitize_text(w['word'])
            if not word:
                continue
            
            start = max(w['start'], last_end)  # prevent overlap
            end = w['end']
            if end <= start:
                end = start + 0.3  # minimum duration
            
            start_ass = self.format_time_ass(start)
            end_ass = self.format_time_ass(end)
            
            dialogue_lines.append(
                f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{word}"
            )
            last_end = end
        
        if not dialogue_lines:
            raise ValueError("No dialogue lines generated")
        
        ass_content += "\n".join(dialogue_lines) + "\n"
        
        with open(output_path, 'w', encoding='utf-8', newline='\r\n') as f:
            f.write(ass_content)
        
        logger.info(f"Generated ASS file with {len(dialogue_lines)} word captions: {output_path}")
        return output_path

def extract_word_timings_whisper(audio_path: str, model_size: str = "base", language: str = "es") -> List[Dict]:
    """Extract word timings using Whisper"""
    try:
        logger.info(f"Loading Whisper model: {model_size}")
        model = whisper.load_model(model_size)
        
        logger.info(f"Transcribing audio: {audio_path} (language: {language})")
        result = model.transcribe(audio_path, word_timestamps=True, task='transcribe', language=language, verbose=False)
        
        word_timings = []
        for segment in result.get('segments', []):
            words = segment.get('words', [])
            for word in words:
                if isinstance(word, dict) and all(key in word for key in ['word', 'start', 'end']):
                    word_timings.append({
                        'word': str(word['word']).strip(),
                        'start': float(word['start']),
                        'end': float(word['end']),
                        'confidence': getattr(word, 'probability', 1.0)
                    })
        
        logger.info(f"Extracted {len(word_timings)} word timings")
        return word_timings
        
    except Exception as e:
        logger.error(f"Error extracting word timings with Whisper: {e}")
        raise

def extract_audio_from_video(video_path: str) -> str:
    """Extract audio from video file for processing"""
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
        temp_audio_path = temp_audio.name
    
    try:
        # Extract audio using ffmpeg-python
        (
            ffmpeg
            .input(video_path)
            .output(temp_audio_path, acodec='pcm_s16le', ac=1, ar='16000')
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.info(f"Extracted audio to: {temp_audio_path}")
        return temp_audio_path
    except ffmpeg.Error as e:
        logger.error(f"Error extracting audio: {e.stderr.decode() if e.stderr else str(e)}")
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        raise

def process_sentence_by_sentence_captions(video_path: str, model_size: str = "base", 
                                        options: Dict = None, language: str = "es") -> str:
    """
    Process video to generate sentence-based word-highlighted captions
    
    Args:
        video_path: Path to the video file
        model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large')
        options: Styling options for captions
        language: Language code for Whisper transcription
    
    Returns:
        Path to the generated ASS caption file
    """
    ensure_temp_directory()
    
    temp_audio_path = None
    
    try:
        # Extract audio for processing
        logger.info("Extracting audio from video...")
        temp_audio_path = extract_audio_from_video(video_path)
        
        # Extract word timings using Whisper
        logger.info("Extracting word timings...")
        word_timings = extract_word_timings_whisper(temp_audio_path, model_size, language)
        
        if not word_timings:
            raise ValueError("No word timings extracted from audio")
        
        # Generate word-by-word caption file
        caption_generator = ImprovedSentenceHighlightGenerator()
        
        video_basename = os.path.splitext(os.path.basename(video_path))[0]
        output_filename = f"{video_basename}_captions_{uuid.uuid4().hex[:8]}.ass"
        output_path = os.path.join(STORAGE_PATH, output_filename)
        
        logger.info("Generating word-by-word ASS subtitle file...")
        return caption_generator.generate_word_by_word_ass(word_timings, output_path, options)
    
    finally:
        # Clean up temporary audio file
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                logger.info(f"Cleaned up temporary audio file: {temp_audio_path}")
            except Exception as e:
                logger.warning(f"Could not remove temporary file {temp_audio_path}: {e}")

def apply_captions_to_video(video_path: str, subtitle_path: str, output_path: str) -> str:
    """Apply ASS captions to video using FFmpeg with better error handling"""
    
    try:
        # Validate inputs
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Use ffmpeg-python for better error handling
        logger.info(f"Applying subtitles to video...")
        logger.info(f"Video: {video_path}")
        logger.info(f"Subtitles: {subtitle_path}")
        logger.info(f"Output: {output_path}")
        
        # Apply subtitles using ffmpeg
        (
            ffmpeg
            .input(video_path)
            .output(
                output_path,
                vf=f"ass='{Path(subtitle_path).as_posix()}':fontsdir='fonts'",
                acodec='copy',
                vcodec='libx264',  # Specify video codec
                preset='medium'    # Balance between speed and quality
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )

        logger.info(f"Successfully created captioned video: {output_path}")
        return output_path
        
    except ffmpeg.Error as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown FFmpeg error"
        logger.error(f"FFmpeg error: {error_msg}")
        raise Exception(f"FFmpeg failed: {error_msg}")
    except Exception as e:
        logger.error(f"Error applying captions: {e}")
        raise

def create_sentence_highlighted_video(video_path: str, model_size: str = "base", 
                                    options: Dict = None, video_type: str = "general") -> str:
    """
    Complete pipeline to create sentence-based word-highlighted video
    
    Args:
        video_path: Path to input video
        model_size: Whisper model size
        options: Caption styling options (will be auto-configured if None)
        video_type: Type of video for font selection (educational, entertainment, news, social, general)
    
    Returns:
        Path to output video with sentence-based word-highlighted captions
    """
    try:
        # Auto-configure font options if not provided
        if options is None:
            # Dynamically select best available font from fonts folder
            font_path = select_best_font()
            
            # Extract font name from path for use with fontsdir (matches filename without extension)
            font_name_only = os.path.splitext(os.path.basename(font_path))[0]
            
            # Use the font name directly for ASS subtitles
            options = {
                'font_name': font_name_only,  # Use filename as font name
                'font_size': 28,
                'primary_color': '&H00FFFF',  # Yellow
                'outline_color': '&H00000000',  # Black
                'back_color': '&H80000000',     # Semi-transparent
                'outline': 3,
                'shadow': 2,
                'alignment': 2,  # Bottom center
                'margin_v': 30
            }
            logger.info(f"Using dynamically selected font: {font_name_only} (from {font_path})")
        else:
            # If options provided, still log the font being used
            font_name = options.get('font_name', 'Unknown')
            logger.info(f"Using provided caption font: {font_name}")
        
        # Step 1: Generate sentence-based word-highlighted captions
        logger.info("Step 1: Generating sentence-based word-highlighted captions...")
        subtitle_path = process_sentence_by_sentence_captions(video_path, model_size, options)
        
        # Step 2: Apply captions to video
        logger.info("Step 2: Applying captions to video...")
        video_basename = os.path.splitext(os.path.basename(video_path))[0]
        output_filename = f"{video_basename}_with_sentence_captions_{uuid.uuid4().hex[:8]}.mp4"
        output_path = os.path.join(STORAGE_PATH, output_filename)
        
        final_video = apply_captions_to_video(video_path, subtitle_path, output_path)
        
        logger.info(f"Successfully created sentence-highlighted video: {final_video}")
        return final_video
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise

# CLI interface for pipeline integration
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add Spanish captions to a video using Whisper + ASS subtitles.")
    parser.add_argument("input", help="Path to the input video file")
    parser.add_argument("-o", "--output", required=True, help="Path for the captioned output video")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper model size (default: base)")
    parser.add_argument("--language", default="es", help="Language for Whisper transcription (default: es)")
    parser.add_argument("--font-size", type=int, default=14, help="Font size for captions (default: 14)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input video not found: {args.input}")
        exit(1)
    
    # Select font from fonts folder
    font_path = select_best_font()
    font_name_only = os.path.splitext(os.path.basename(font_path))[0]
    
    caption_options = {
        'font_name': font_name_only,
        'font_size': args.font_size,
        'primary_color': '&H00FFFFFF',  # White
        'outline_color': '&H00000000',  # Black
        'back_color': '&H80000000',     # Semi-transparent black
        'outline': 2,
        'shadow': 1,
        'alignment': 2,  # Bottom center
        'margin_v': 35
    }
    
    print(f"  Caption Video")
    print(f"  Input  : {args.input}")
    print(f"  Output : {args.output}")
    print(f"  Font   : {font_name_only} ({font_path})")
    print(f"  Model  : {args.model}")
    print(f"  Language: {args.language}")
    
    try:
        # Step 1: Generate ASS subtitles
        subtitle_path = process_sentence_by_sentence_captions(
            args.input, args.model, caption_options, args.language
        )
        
        # Step 2: Apply captions and write to final output path
        apply_captions_to_video(args.input, subtitle_path, args.output)
        
        print(f"  ✅ Captioned video saved: {args.output}")
        
    except Exception as e:
        print(f"  ❌ Captioning failed: {e}")
        logger.exception("Captioning pipeline error")
        exit(1)

