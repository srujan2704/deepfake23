import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import matplotlib.pyplot as plt
import seaborn as sns

# Load your existing dataset
df = pd.read_csv('data_set.csv')

# Display the dataset
print("Dataset of 30 videos:")
print(df.to_string(index=False))

# Calculate accuracy metrics - FIXED COLUMN NAMES
accuracy = df['Correct'].mean() * 100
real_accuracy = df[df['True_Label'] == 'Real']['Correct'].mean() * 100
fake_accuracy = df[df['True_Label'] == 'Fake']['Correct'].mean() * 100

print(f'\nOverall Accuracy: {accuracy:.2f}%')
print(f'Real Videos Accuracy: {real_accuracy:.2f}%')
print(f'Fake Videos Accuracy: {fake_accuracy:.2f}%')

# Create confusion matrix - FIXED COLUMN NAMES
confusion_matrix = pd.crosstab(df['True_Label'], df['Predicted_Label'], 
                              rownames=['Actual'], colnames=['Predicted'])

print("\nConfusion Matrix:")
print(confusion_matrix)

# Calculate additional metrics
total_real = len(df[df['True_Label'] == 'Real'])
total_fake = len(df[df['True_Label'] == 'Fake'])
true_positives = len(df[(df['True_Label'] == 'Real') & (df['Predicted_Label'] == 'Real')])
true_negatives = len(df[(df['True_Label'] == 'Fake') & (df['Predicted_Label'] == 'Fake')])
false_positives = len(df[(df['True_Label'] == 'Fake') & (df['Predicted_Label'] == 'Real')])
false_negatives = len(df[(df['True_Label'] == 'Real') & (df['Predicted_Label'] == 'Fake')])

print(f"\nDetailed Metrics:")
print(f"True Positives: {true_positives}")
print(f"True Negatives: {true_negatives}")
print(f"False Positives: {false_positives}")
print(f"False Negatives: {false_negatives}")

# Create visualizations
def generate_visualizations():
    # 1. Accuracy Bar Chart
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        x=['Overall', 'Real Videos', 'Fake Videos'],
        y=[accuracy, real_accuracy, fake_accuracy],
        marker_color=['blue', 'green', 'red'],
        text=[f'{accuracy:.1f}%', f'{real_accuracy:.1f}%', f'{fake_accuracy:.1f}%'],
        textposition='auto'
    ))
    fig1.update_layout(
        title='Accuracy Metrics',
        xaxis_title='Category',
        yaxis_title='Accuracy (%)',
        yaxis=dict(range=[0, 100])
    )
    
    # 2. Confusion Matrix Heatmap
    fig2 = go.Figure(data=go.Heatmap(
        z=confusion_matrix.values,
        x=confusion_matrix.columns.tolist(),
        y=confusion_matrix.index.tolist(),
        colorscale='Blues',
        text=confusion_matrix.values,
        texttemplate="%{text}",
        textfont={"size": 16}
    ))
    fig2.update_layout(
        title='Confusion Matrix',
        xaxis_title='Predicted Label',
        yaxis_title='True Label'
    )
    
    # 3. Distribution of predictions
    fig3 = go.Figure()
    fig3.add_trace(go.Pie(
        labels=df['Predicted_Label'].value_counts().index,
        values=df['Predicted_Label'].value_counts().values,
        hole=0.3
    ))
    fig3.update_layout(title='Distribution of Predictions')
    
    # 4. Performance by video type
    performance_data = pd.DataFrame({
        'Type': ['Real', 'Fake'],
        'Accuracy': [real_accuracy, fake_accuracy],
        'Count': [total_real, total_fake]
    })
    
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(
        x=performance_data['Type'],
        y=performance_data['Accuracy'],
        marker_color=['green', 'red'],
        text=performance_data['Accuracy'].round(1).astype(str) + '%',
        textposition='auto'
    ))
    fig4.update_layout(
        title='Accuracy by Video Type',
        xaxis_title='Video Type',
        yaxis_title='Accuracy (%)',
        yaxis=dict(range=[0, 100])
    )
    
    return fig1, fig2, fig3, fig4

# Generate and show plots
try:
    fig1, fig2, fig3, fig4 = generate_visualizations()
    
    # Save plots as HTML files
    fig1.write_html("accuracy_metrics.html")
    fig2.write_html("confusion_matrix.html")
    fig3.write_html("predictions_distribution.html")
    fig4.write_html("performance_by_type.html")
    
    print("\nGraphs generated successfully! Check the HTML files:")
    print("- accuracy_metrics.html")
    print("- confusion_matrix.html")
    print("- predictions_distribution.html")
    print("- performance_by_type.html")
    
    # If you want to show them interactively
    # fig1.show()
    # fig2.show()
    # fig3.show()
    # fig4.show()
    
except Exception as e:
    print(f"Error generating graphs: {e}")
    print("Make sure you have plotly installed: pip install plotly")