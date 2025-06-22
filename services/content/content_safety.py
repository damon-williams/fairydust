# services/content/content_safety.py
import re
from typing import List, Tuple
from models import StoryGenerationRequest, TargetAudience

class ContentSafetyFilter:
    """Content safety and appropriateness filtering for stories"""
    
    # Words/phrases to flag for different audiences
    INAPPROPRIATE_WORDS = [
        "violence", "violent", "blood", "death", "kill", "murder", "weapon", "gun", "knife",
        "scary", "frightening", "terrifying", "nightmare", "monster", "demon", "ghost",
        "hate", "stupid", "idiot", "dumb", "ugly", "fat", "loser"
    ]
    
    ADULT_ONLY_THEMES = [
        "alcohol", "beer", "wine", "drunk", "drinking", "bar", "cocktail",
        "romantic", "dating", "kiss", "love", "relationship", "marriage", "wedding",
        "money", "rich", "poor", "expensive", "cheap", "cost", "price", "buy", "sell"
    ]
    
    def __init__(self):
        pass
    
    def validate_request(self, request: StoryGenerationRequest) -> Tuple[bool, List[str]]:
        """Validate story generation request for safety"""
        issues = []
        
        # Check character names for inappropriate content
        for char in request.characters:
            if self._contains_inappropriate_content(char.name):
                issues.append(f"Character name '{char.name}' contains inappropriate content")
            
            # Check character traits
            for trait in char.traits:
                if self._contains_inappropriate_content(trait):
                    issues.append(f"Character trait '{trait}' contains inappropriate content")
        
        # Check setting for inappropriate content
        if request.setting and self._contains_inappropriate_content(request.setting):
            issues.append("Setting contains inappropriate content")
        
        # Check theme for inappropriate content
        if request.theme and self._contains_inappropriate_content(request.theme):
            issues.append("Theme contains inappropriate content")
        
        # Check custom prompt for inappropriate content
        if request.custom_prompt and self._contains_inappropriate_content(request.custom_prompt):
            issues.append("Custom prompt contains inappropriate content")
        
        # Check age appropriateness
        child_characters = [char for char in request.characters if char.age and char.age < 13]
        if child_characters and request.target_audience != TargetAudience.CHILD:
            # Suggest child-appropriate content when children are involved
            pass
        
        # Check for adult themes with child audience
        if request.target_audience == TargetAudience.CHILD:
            adult_themes = self._check_adult_themes(request)
            if adult_themes:
                issues.extend([f"Adult theme detected for child audience: {theme}" for theme in adult_themes])
        
        return len(issues) == 0, issues
    
    def filter_generated_content(self, content: str, target_audience: TargetAudience) -> Tuple[str, List[str]]:
        """Filter and clean generated story content"""
        warnings = []
        filtered_content = content
        
        # Check for inappropriate words
        inappropriate_found = self._find_inappropriate_words(content)
        if inappropriate_found:
            warnings.extend([f"Inappropriate content detected: {word}" for word in inappropriate_found])
            # In a production system, you might want to replace or modify the content
        
        # Check content length is appropriate
        word_count = len(content.split())
        if word_count < 100:
            warnings.append("Story content seems too short")
        elif word_count > 2000:
            warnings.append("Story content seems too long")
        
        # Check for positive ending (basic sentiment analysis)
        if not self._has_positive_ending(content):
            warnings.append("Story may not have a positive ending")
        
        return filtered_content, warnings
    
    def _contains_inappropriate_content(self, text: str) -> bool:
        """Check if text contains inappropriate content"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Check for inappropriate words
        for word in self.INAPPROPRIATE_WORDS:
            if word in text_lower:
                return True
        
        # Check for profanity patterns
        profanity_patterns = [
            r'\b(damn|hell|crap|stupid|idiot|dumb|ugly)\b',
            r'\b(hate|kill|murder|death|blood)\b'
        ]
        
        for pattern in profanity_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _check_adult_themes(self, request: StoryGenerationRequest) -> List[str]:
        """Check for adult themes inappropriate for children"""
        adult_themes = []
        
        # Combine all text to check
        all_text = []
        if request.setting:
            all_text.append(request.setting)
        if request.theme:
            all_text.append(request.theme)
        if request.custom_prompt:
            all_text.append(request.custom_prompt)
        
        for char in request.characters:
            all_text.extend(char.traits)
        
        combined_text = " ".join(all_text).lower()
        
        for theme in self.ADULT_ONLY_THEMES:
            if theme in combined_text:
                adult_themes.append(theme)
        
        return adult_themes
    
    def _find_inappropriate_words(self, content: str) -> List[str]:
        """Find inappropriate words in content"""
        if not content:
            return []
        
        content_lower = content.lower()
        found_words = []
        
        for word in self.INAPPROPRIATE_WORDS:
            if word in content_lower:
                found_words.append(word)
        
        return found_words
    
    def _has_positive_ending(self, content: str) -> bool:
        """Basic check for positive story ending"""
        if not content:
            return False
        
        # Get last 200 characters
        ending = content[-200:].lower()
        
        positive_indicators = [
            "happy", "joy", "smile", "laugh", "love", "friendship", "together",
            "success", "victory", "overcome", "learned", "grew", "better",
            "grateful", "thankful", "wonderful", "amazing", "perfect", "beautiful"
        ]
        
        negative_indicators = [
            "sad", "cry", "tears", "alone", "lost", "failed", "never", "impossible",
            "hopeless", "terrible", "awful", "worst", "hate", "angry"
        ]
        
        positive_count = sum(1 for word in positive_indicators if word in ending)
        negative_count = sum(1 for word in negative_indicators if word in ending)
        
        return positive_count > negative_count
    
    def get_content_guidelines(self, target_audience: TargetAudience) -> str:
        """Get content guidelines for the target audience"""
        guidelines = {
            TargetAudience.CHILD: """
- Use simple, age-appropriate language
- Focus on positive themes like friendship, kindness, and learning
- Avoid scary, violent, or inappropriate content
- Include fun, engaging elements that children enjoy
- End with a positive, uplifting conclusion
            """.strip(),
            
            TargetAudience.FAMILY: """
- Content suitable for all family members
- Balance entertainment for different ages
- Include positive role models and relationships
- Avoid controversial or divisive topics
- Promote family values and togetherness
            """.strip(),
            
            TargetAudience.ADULT: """
- More complex themes and situations allowed
- Can include mild romantic elements
- May address real-world challenges
- Maintain appropriate language and content
- Focus on meaningful, engaging storytelling
            """.strip()
        }
        
        return guidelines.get(target_audience, guidelines[TargetAudience.FAMILY])

# Global content safety filter instance
content_safety_filter = ContentSafetyFilter()