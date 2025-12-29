from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Project, Task, UserProfile, Industry


class ProjectForm(forms.ModelForm):
    """Form for creating and editing projects"""
    
    class Meta:
        model = Project
        fields = ['name', 'description', 'status', 'priority', 'start_date', 'end_date', 
                  'project_manager', 'industry', 'project_type', 'budget_min', 'budget_max', 'deadline']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-group input',
                'placeholder': 'Enter project name'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-group input',
                'placeholder': 'Describe your project...',
                'rows': 4
            }),
            'status': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'start_date': forms.DateInput(attrs={
                'class': 'form-group input',
                'type': 'date'
            }),
            'end_date': forms.DateInput(attrs={
                'class': 'form-group input',
                'type': 'date'
            }),
            'project_manager': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'industry': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'project_type': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'budget_min': forms.NumberInput(attrs={
                'class': 'form-group input',
                'step': '0.01',
                'placeholder': 'Minimum budget'
            }),
            'budget_max': forms.NumberInput(attrs={
                'class': 'form-group input',
                'step': '0.01',
                'placeholder': 'Maximum budget'
            }),
            'deadline': forms.DateInput(attrs={
                'class': 'form-group input',
                'type': 'date'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter project_manager to show users (or limit to project managers if needed)
        if user:
            # You can customize this queryset based on your needs
            from django.contrib.auth import get_user_model
            User = get_user_model()
            self.fields['project_manager'].queryset = User.objects.all()
        
        # Industry queryset - show all industries
        self.fields['industry'].queryset = Industry.objects.all()
        
        # Make new fields optional (they're already nullable in model, but ensure empty is allowed)
        self.fields['project_manager'].required = False
        self.fields['industry'].required = False
        self.fields['project_type'].required = False
        self.fields['budget_min'].required = False
        self.fields['budget_max'].required = False
        self.fields['deadline'].required = False


class TaskForm(forms.ModelForm):
    """Form for creating and editing tasks"""
    
    class Meta:
        model = Task
        fields = ['title', 'description', 'project', 'assignee', 'status', 'priority', 'due_date', 'estimated_hours']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-group input',
                'placeholder': 'Enter task title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-group input',
                'placeholder': 'Describe the task...',
                'rows': 3
            }),
            'project': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'assignee': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'status': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-group input'
            }),
            'due_date': forms.DateTimeInput(attrs={
                'class': 'form-group input',
                'type': 'datetime-local'
            }),
            'estimated_hours': forms.NumberInput(attrs={
                'class': 'form-group input',
                'step': '0.5',
                'min': '0'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Only show projects owned by the user
        if user:
            self.fields['project'].queryset = Project.objects.filter(owner=user)
            # Assignee can be any user (or you can limit this)
            from django.contrib.auth import get_user_model
            User = get_user_model()
            self.fields['assignee'].queryset = User.objects.all()


class CustomUserCreationForm(UserCreationForm):
    """Custom signup form with role selection"""
    role = forms.ChoiceField(
        choices=[
            ('project_manager', 'Project Manager'),
            ('recruitment_agent', 'Recruitment Agent'),
            ('frontline_agent', 'Frontline Agent'),
            ('marketing_agent', 'Marketing Agent'),
        ],
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-group input',
            'style': 'width: 100%; padding: 0.75rem 1rem; border: 2px solid var(--border-color); border-radius: var(--radius-md); font-size: 1rem;'
        }),
        help_text='Select your role in the organization'
    )
    
    class Meta:
        model = User
        fields = ('username', 'password1', 'password2', 'role')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove help_text from password fields so they only show on validation errors
        self.fields['password1'].help_text = None
        self.fields['password2'].help_text = None
        
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            # Create or update user profile with role
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.role = self.cleaned_data['role']
            profile.save()
        return user

