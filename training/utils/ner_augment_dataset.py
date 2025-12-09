
"""
Augment dataset by adding lowercase versions of examples
Creates 70% lowercase, 30% original by adding lowercase copies
"""

import pandas as pd

INPUT_CSV = "ner_data_fixed_autofixed.csv"
OUTPUT_CSV = "ner_data_augmented.csv"


def create_lowercase_version(text, entity_text, start_idx, end_idx, label):
    """Create lowercase version of a training example."""
    
    # Convert to lowercase
    text_lower = text.lower()
    entity_lower = text_lower[start_idx:end_idx]
    
    return {
        'text': text_lower,
        'entity_text': entity_lower,
        'entity_label': label,
        'start_idx': start_idx,
        'end_idx': end_idx
    }


def augment_with_lowercase(df):
    """Add lowercase versions to achieve 70/30 distribution."""
    
    print(f"📊 Original dataset: {len(df)} rows")
    
    # Keep all original data
    augmented_rows = df.to_dict('records')
    
    # Group by unique text
    unique_texts = df.groupby('text')
    original_count = len(unique_texts)
    
    print(f"   Unique sentences: {original_count}")
    
    # To get 70% lowercase, we need to add lowercase copies
    # If we have N original sentences, we want:
    # - N original (will become 30%)
    # - 2.33*N lowercase (will become 70%)
    # Total = 3.33*N sentences
    
    lowercase_multiplier = 2.33  # This gives us ~70% lowercase
    
    lowercase_added = 0
    
    for text, group in unique_texts:
        # Skip if already lowercase
        if text.islower():
            continue
        
        # Add lowercase versions
        for _, row in group.iterrows():
            if pd.isna(row['entity_label']) or row['entity_label'] == 'NONE':
                augmented_rows.append({
                    'text': text.lower(),
                    'entity_text': '',
                    'entity_label': 'NONE',
                    'start_idx': 0,
                    'end_idx': 0
                })
                continue
            
            start_idx = int(row['start_idx'])
            end_idx = int(row['end_idx'])
            
            lowercase_row = create_lowercase_version(
                text, 
                row['entity_text'],
                start_idx,
                end_idx,
                row['entity_label']
            )
            
            # Add 2 copies to reach 70% ratio
            augmented_rows.append(lowercase_row)
            augmented_rows.append(lowercase_row.copy())
            
            lowercase_added += 2
    
    df_augmented = pd.DataFrame(augmented_rows)
    
    # Remove exact duplicates
    df_augmented = df_augmented.drop_duplicates()
    
    # Calculate distribution
    texts = df_augmented['text'].unique()
    lowercase_count = sum(1 for t in texts if t.islower() and t.strip())
    total_count = len(texts)
    
    actual_ratio = lowercase_count / total_count if total_count > 0 else 0
    
    print(f"\n✅ Augmented dataset: {len(df_augmented)} rows")
    print(f"   Added {lowercase_added} lowercase examples")
    print(f"   Unique sentences: {total_count}")
    print(f"   Lowercase: {lowercase_count} ({actual_ratio:.1%})")
    print(f"   Original case: {total_count - lowercase_count} ({1-actual_ratio:.1%})")
    
    return df_augmented


def main():
    print("="*80)
    print("LOWERCASE AUGMENTATION")
    print("="*80)
    print("\nStrategy: Add lowercase copies to reach 70/30 distribution")
    
    # Load
    print(f"\n📂 Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    
    # Augment
    print(f"\n🔄 Adding lowercase versions...")
    df_augmented = augment_with_lowercase(df)
    
    # Show entity statistics
    print(f"\n📊 Entity Statistics:")
    entity_counts = df_augmented['entity_label'].value_counts()
    for label, count in entity_counts.items():
        if label != 'NONE':
            print(f"   {label:15s}: {count:4d} examples")
    
    # Save
    print(f"\n💾 Saving to {OUTPUT_CSV}...")
    df_augmented.to_csv(OUTPUT_CSV, index=False)
    
    print("\n" + "="*80)
    print("✅ DONE!")
    print("="*80)
    print(f"\nAugmented data: {OUTPUT_CSV}")
    print(f"Total size: {len(df_augmented)} rows (from {len(df)} original)")
    print(f"\nUpdate train_ner_autofix.py:")
    print(f"  CSV_FILE = '{OUTPUT_CSV}'")
    print(f"\nThen retrain: python train_ner_autofix.py")


if __name__ == "__main__":
    main()