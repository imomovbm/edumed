from django.contrib import admin
from .models import UserProfile 
from .models import PasswordResetRequest

# Create a custom ModelAdmin for better display and filtering
class UserProfileAdmin(admin.ModelAdmin):
    # Fields to display in the list view (User info + Profile info)
    list_display = (
        'user',
        'full_name', 
        'email', 
        'role', 
        'phone', 
        'get_gender_display',
        'date_of_birth',   # <-- NEW: Display Date of Birth
        'join_date',       # <-- NEW: Display Join Date
        'region',
        'otm',
    )
    
    # Fields to use for searching
    search_fields = (
        'user__first_name', 
        'user__last_name', 
        'user__email', 
        'phone',
        'region',
        'otm',
    )
    
    # Fields to use for filtering in the sidebar
    list_filter = (
        'role', 
        'gender', 
        'region', 
        'otm', 
        'join_date',       # <-- NEW: Allow filtering by join date
    )
    
    # Read-only fields in the detail view
    readonly_fields = ('join_date',) # <-- Updated: Make join_date read-only
    
    # Ordering the list by role and then by join date (newest first)
    ordering = ('role', '-join_date',) 

    # --- Custom Methods to retrieve User data ---
    
    def full_name(self, obj):
        # Combines first and last name from the linked User model
        return f"{obj.user.first_name} {obj.user.last_name}"
    full_name.short_description = 'F.I.SH'

    def email(self, obj):
        # Gets the email from the linked User model
        return obj.user.email
    email.short_description = 'Email'

    # Ensure the columns are sortable by the underlying User fields
    full_name.admin_order_field = 'user__last_name'
    email.admin_order_field = 'user__email'

# Register the UserProfile model with the custom admin class
admin.site.register(UserProfile, UserProfileAdmin)


admin.site.register(PasswordResetRequest)