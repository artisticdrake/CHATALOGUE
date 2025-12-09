
"""
Multi-Entity NER Training Script with Auto-Fix for Indices
"""

import pandas as pd
import spacy
from spacy.training import Example
from spacy.util import minibatch, compounding
import random
from pathlib import Path
import sys

# Configuration
CSV_FILE = "ner_data_augmented.csv"  # Will auto-fix indices
OUTPUT_MODEL = "course_ner_model"
N_ITER = 70
TEST_SPLIT = 0.2

# Entity labels
ENTITY_LABELS = [
    "INSTRUCTOR",
    "COURSE_CODE", 
    "COURSE_NAME",
    "WEEKDAY",
    "TIME",
    "BUILDING",
    "SECTION"
]


def auto_fix_indices(csv_file):
    """Auto-fix entity indices while loading."""
    print(f"🔧 Auto-fixing indices...")
    df = pd.read_csv(csv_file)
    
    fixed_rows = []
    errors = 0
    
    for idx, row in df.iterrows():
        text = str(row['text'])
        entity_text = str(row['entity_text']).strip()
        entity_label = row['entity_label']
        
        # Skip non-entities
        if pd.isna(entity_label) or entity_label == 'NONE' or not entity_text or entity_text == 'nan':
            fixed_rows.append({
                'text': text,
                'entity_text': '',
                'entity_label': 'NONE',
                'start_idx': 0,
                'end_idx': 0
            })
            continue
        
        # Find entity in text (case-insensitive)
        start_idx = text.lower().find(entity_text.lower())
        
        if start_idx == -1:
            # Try case-sensitive
            start_idx = text.find(entity_text)
        
        if start_idx == -1:
            errors += 1
            continue  # Skip if not found
        
        end_idx = start_idx + len(entity_text)
        
        # Verify extraction
        extracted = text[start_idx:end_idx]
        if extracted.lower() != entity_text.lower():
            errors += 1
            continue
        
        fixed_rows.append({
            'text': text,
            'entity_text': entity_text,
            'entity_label': entity_label,
            'start_idx': start_idx,
            'end_idx': end_idx
        })
    
    if errors > 0:
        print(f"   ⚠️  Skipped {errors} problematic entities")
    
    df_fixed = pd.DataFrame(fixed_rows)
    
    # Remove duplicate entities (same text + entity + label + indices)
    print(f"🔍 Removing duplicates...")
    original_len = len(df_fixed)
    df_fixed = df_fixed.drop_duplicates(subset=['text', 'entity_text', 'entity_label', 'start_idx', 'end_idx'])
    duplicates_removed = original_len - len(df_fixed)
    if duplicates_removed > 0:
        print(f"   🗑️  Removed {duplicates_removed} duplicate annotations")
    
    # Save fixed dataset
    fixed_csv_path = csv_file.replace('.csv', '_autofixed.csv')
    df_fixed.to_csv(fixed_csv_path, index=False)
    print(f"💾 Saved fixed dataset to: {fixed_csv_path}")
    
    return df_fixed


def load_training_data(csv_file):
    """Load and split data into train/test sets."""
    print(f"📂 Loading training data from {csv_file}...")
    
    # Auto-fix indices
    df = auto_fix_indices(csv_file)
    
    # Group by text to get all entities per sentence
    grouped = df.groupby('text')
    
    all_data = []
    
    for text, group in grouped:
        entities = []
        seen_entities = set()  # Track unique entities per text
        
        for _, row in group.iterrows():
            if pd.isna(row['entity_label']) or row['entity_label'] == 'NONE':
                continue
            
            if pd.isna(row['start_idx']) or pd.isna(row['end_idx']):
                continue
                
            start = int(row['start_idx'])
            end = int(row['end_idx'])
            label = row['entity_label']
            
            # Create unique key for this entity
            entity_key = (start, end, label)
            
            # Skip if duplicate
            if entity_key in seen_entities:
                continue
            
            seen_entities.add(entity_key)
            entities.append((start, end, label))
        
        all_data.append((text, {"entities": entities}))
    
    # Filter out problematic patterns
    problematic_patterns = [
        r'2pm-4pm', r'\d+pm-\d+pm', r'\d+am-\d+am',  # Time ranges
        r'MonWedFri', r'TueThu', r'monwed',  # Concatenated days
        r'Wed\.', r'Mon\.', r'Tue\.', r'Thu\.', r'Fri\.', r'Sat\.', r'Sun\.',  # Periods
    ]
    
    import re
    filtered_data = []
    skipped = 0
    
    for text, annot in all_data:
        # Check if text matches any problematic pattern
        is_bad = False
        for pattern in problematic_patterns:
            if re.search(pattern, text):
                is_bad = True
                skipped += 1
                break
        
        if not is_bad:
            filtered_data.append((text, annot))
    
    all_data = filtered_data
    
    if skipped > 0:
        print(f"   🗑️  Filtered out {skipped} problematic examples")
    
    # Shuffle and split
    random.shuffle(all_data)
    split_idx = int(len(all_data) * (1 - TEST_SPLIT))
    
    train_data = all_data[:split_idx]
    test_data = all_data[split_idx:]
    
    print(f"✅ Loaded {len(all_data)} total examples")
    print(f"   Training: {len(train_data)} examples ({(1-TEST_SPLIT)*100:.0f}%)")
    print(f"   Testing:  {len(test_data)} examples ({TEST_SPLIT*100:.0f}%)")
    
    # Show statistics for training set
    entity_counts = {}
    for _, annot in train_data:
        for _, _, label in annot["entities"]:
            entity_counts[label] = entity_counts.get(label, 0) + 1
    
    print(f"\n📊 Training Set Entity Statistics:")
    for label in sorted(entity_counts.keys()):
        print(f"   {label:15s}: {entity_counts[label]:4d} examples")
    
    return train_data, test_data


def train_ner(training_data, n_iter=75):
    """Train spaCy NER model."""
    
    print(f"\n🎓 Starting training...")
    print(f"   Iterations: {n_iter}")
    print(f"   Examples: {len(training_data)}")
    print(f"   Estimated time: ~{n_iter//10}-{n_iter//5} minutes...")
    
    # Create blank English model
    nlp = spacy.blank("en")
    
    # Add NER pipe
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner")
    else:
        ner = nlp.get_pipe("ner")
    
    # Add entity labels
    for label in ENTITY_LABELS:
        ner.add_label(label)
    
    # Get names of other pipes to disable them during training
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    
    # Train only NER
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        
        for iteration in range(n_iter):
            random.shuffle(training_data)
            losses = {}
            
            # Batch training data
            batches = minibatch(training_data, size=compounding(4.0, 32.0, 1.001))
            
            for batch in batches:
                examples = []
                for text, annotations in batch:
                    doc = nlp.make_doc(text)
                    example = Example.from_dict(doc, annotations)
                    examples.append(example)
                
                nlp.update(examples, drop=0.35, losses=losses, sgd=optimizer)
            
            # Print progress
            if (iteration + 1) % 5 == 0:
                progress = (iteration + 1) / n_iter * 100
                bar_length = 30
                filled = int(bar_length * (iteration + 1) / n_iter)
                bar = '█' * filled + '░' * (bar_length - filled)
                print(f"   [{bar}] {progress:5.1f}% - Iteration {iteration + 1:2d}/{n_iter} - Loss: {losses['ner']:6.2f}")
    
    print(f"\n✅ Training complete!")
    return nlp


def evaluate_model(nlp, test_data):
    """Evaluate model on test set with detailed metrics."""
    
    print(f"\n📊 EVALUATING MODEL ON TEST SET")
    print("="*80)
    
    # Manual metric calculation
    metrics = {label: {'tp': 0, 'fp': 0, 'fn': 0} for label in ENTITY_LABELS}
    metrics['OVERALL'] = {'tp': 0, 'fp': 0, 'fn': 0}
    
    errors = []
    
    for text, annotations in test_data:
        # Get predictions
        pred_doc = nlp(text)
        
        # Gold entities
        gold_ents = set()
        for start, end, label in annotations["entities"]:
            gold_ents.add((start, end, label))
        
        # Predicted entities
        pred_ents = set()
        for ent in pred_doc.ents:
            pred_ents.add((ent.start_char, ent.end_char, ent.label_))
        
        # Calculate metrics per entity type
        for start, end, label in gold_ents:
            if (start, end, label) in pred_ents:
                # True positive
                metrics[label]['tp'] += 1
                metrics['OVERALL']['tp'] += 1
            else:
                # False negative (missed)
                metrics[label]['fn'] += 1
                metrics['OVERALL']['fn'] += 1
                
                if len(errors) < 20:
                    errors.append({
                        'type': 'False Negative (Missed)',
                        'text': text,
                        'entity': text[start:end],
                        'label': label,
                        'start': start,
                        'end': end
                    })
        
        for start, end, label in pred_ents:
            if (start, end, label) not in gold_ents:
                # False positive (wrong prediction)
                metrics[label]['fp'] += 1
                metrics['OVERALL']['fp'] += 1
                
                if len(errors) < 20:
                    errors.append({
                        'type': 'False Positive (Wrong)',
                        'text': text,
                        'entity': text[start:end],
                        'label': label,
                        'start': start,
                        'end': end
                    })
    
    # Calculate precision, recall, F1 for each entity type
    print(f"\n📋 DETAILED ACCURACY METRICS")
    print("="*80)
    print(f"{'Entity':15s} {'TP':>6s} {'FP':>6s} {'FN':>6s} {'Precision':>10s} {'Recall':>10s} {'F1-Score':>10s}")
    print("-" * 80)
    
    results = {}
    
    for label in ENTITY_LABELS:
        tp = metrics[label]['tp']
        fp = metrics[label]['fp']
        fn = metrics[label]['fn']
        
        # Calculate metrics
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        results[label] = {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'tp': tp,
            'fp': fp,
            'fn': fn
        }
        
        print(f"{label:15s} {tp:6d} {fp:6d} {fn:6d} {precision:9.1%} {recall:9.1%} {f1:9.1%}")
    
    # Overall metrics
    print("-" * 80)
    tp = metrics['OVERALL']['tp']
    fp = metrics['OVERALL']['fp']
    fn = metrics['OVERALL']['fn']
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    results['OVERALL'] = {
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'tp': tp,
        'fp': fp,
        'fn': fn
    }
    
    print(f"{'OVERALL':15s} {tp:6d} {fp:6d} {fn:6d} {precision:9.1%} {recall:9.1%} {f1:9.1%}")
    print("="*80)
    
    # Summary box
    print(f"\n" + "┌" + "─"*78 + "┐")
    print(f"│ {'📊 OVERALL MODEL PERFORMANCE':^76s} │")
    print(f"├" + "─"*78 + "┤")
    print(f"│ {'Precision:':<20s} {precision:>6.1%} {'(How many predictions are correct)':^48s} │")
    print(f"│ {'Recall:':<20s} {recall:>6.1%} {'(How many entities were found)':^48s} │")
    print(f"│ {'F1-Score:':<20s} {f1:>6.1%} {'(Overall accuracy)':^48s} │")
    print(f"└" + "─"*78 + "┘")
    
    # Error examples
    if errors:
        print(f"\n❌ SAMPLE ERRORS (showing {min(len(errors), 20)} examples)")
        print("="*80)
        
        for i, err in enumerate(errors[:20], 1):
            print(f"\n{i}. {err['type']}")
            print(f"   Query: '{err['text']}'")
            print(f"   Entity: '{err['entity']}' [{err['label']}]")
            print(f"   Position: {err['start']}:{err['end']}")
    
    return results


def test_on_examples(nlp, examples):
    """Test model on specific examples."""
    print(f"\n🧪 TESTING ON SAMPLE QUERIES")
    print("="*80)
    
    for text in examples:
        doc = nlp(text)
        print(f"\n📝 '{text}'")
        
        if doc.ents:
            for ent in doc.ents:
                print(f"   ✓ {ent.text:20s} → {ent.label_}")
        else:
            print(f"   (No entities found)")


def main():
    """Main training pipeline."""
    
    print("=" * 80)
    print("🎯 COURSE CHATBOT - MULTI-ENTITY NER TRAINING")
    print("=" * 80)
    
    # Load and split data
    train_data, test_data = load_training_data(CSV_FILE)
    
    if len(train_data) == 0:
        print("❌ No training data found!")
        sys.exit(1)
    
    # Train
    nlp = train_ner(train_data, n_iter=N_ITER)
    
    # Evaluate on test set
    scores = evaluate_model(nlp, test_data)
    
    # Test on sample queries
    test_examples = [
        "Does Goh teach CS 575?",
        "What about differential equations?",
        "Who teaches MA 226 on Monday at 6pm?",
        "Classes in CAS building section A1",
        "Is operating systems taught by Professor Moore?",
        "What time is the Tuesday class?",
        "Hello there!",
    ]
    test_on_examples(nlp, test_examples)
    
    # Save model
    output_path = Path(OUTPUT_MODEL)
    nlp.to_disk(output_path)
    print(f"\n💾 Model saved to: {output_path}")
    
    overall = scores['OVERALL']
    
    print("\n" + "=" * 80)
    print("✅ TRAINING COMPLETE!")
    print("=" * 80)
    
    print(f"\n┌{'─'*78}┐")
    print(f"│ {'🎯 FINAL MODEL PERFORMANCE':^76s} │")
    print(f"├{'─'*78}┤")
    print(f"│                                                                              │")
    print(f"│   {'Precision:':<15s} {overall['precision']:>6.1%}  {'← % of predictions that are correct':>50s}  │")
    print(f"│   {'Recall:':<15s} {overall['recall']:>6.1%}  {'← % of actual entities found':>50s}  │")
    print(f"│   {'F1-Score:':<15s} {overall['f1']:>6.1%}  {'← Overall accuracy (higher is better)':>50s}  │")
    print(f"│                                                                              │")
    print(f"│   {'True Positives:':<15s} {overall['tp']:>6d}  {'← Correct predictions':>50s}  │")
    print(f"│   {'False Positives:':<15s} {overall['fp']:>6d}  {'← Wrong predictions':>50s}  │")
    print(f"│   {'False Negatives:':<15s} {overall['fn']:>6d}  {'← Missed entities':>50s}  │")
    print(f"│                                                                              │")
    print(f"└{'─'*78}┘")
    
    # Interpretation guide
    print(f"\n📖 INTERPRETATION GUIDE:")
    if overall['f1'] >= 0.90:
        print(f"   ⭐⭐⭐⭐⭐ EXCELLENT! (90%+) - Production ready!")
    elif overall['f1'] >= 0.80:
        print(f"   ⭐⭐⭐⭐ GOOD (80-90%) - Works well, minor improvements possible")
    elif overall['f1'] >= 0.70:
        print(f"   ⭐⭐⭐ OKAY (70-80%) - Usable but needs more training data")
    else:
        print(f"   ⭐⭐ NEEDS WORK (<70%) - Add more training examples")
    
    print(f"\nTo use the model:")
    print(f"  import spacy")
    print(f"  nlp = spacy.load('{OUTPUT_MODEL}')")
    print(f"  doc = nlp('Does Goh teach CS 575?')")
    print(f"  for ent in doc.ents:")
    print(f"      print(ent.text, ent.label_)")


if __name__ == "__main__":
    main()