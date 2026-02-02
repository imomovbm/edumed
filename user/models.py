from django.contrib.auth.models import User
from django.db import models
from datetime import date # Import date for validation/defaults

# Create your models here.
class UserProfile(models.Model):
    # Field Choices
    ROLE_CHOICES = [
        ('superadmin', 'SuperAdmin'),
        ('teacher', 'O\'qituvchi'),
        ('student', 'Talaba'),
        ('moder', 'Moder'),
    ]

    GENDER_CHOICES = [
        (1, 'Erkak'),  # Male
        (0, 'Ayol'),   # Female
    ]

    # Required Fields
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student') 
    phone = models.CharField(max_length=30, blank=True, null=True)

    # New Fields from Registration Form
    gender = models.IntegerField(choices=GENDER_CHOICES, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    otm = models.CharField(max_length=100, verbose_name="Ta'lim Muassasasi", null=True, blank=True)
    
    # --- NEW FIELDS ---
    date_of_birth = models.DateField(verbose_name="Tug'ilgan sana", null=True, blank=True)
    # automatically sets the date when the object is first created
    join_date = models.DateField(auto_now_add=True) 

    def __str__(self):
        return f"{self.user.username} : {self.role}"



class PasswordResetRequest(models.Model):
    # This stores the input the user provided (email or phone)
    contact_input = models.CharField(max_length=150, verbose_name="Email yoki Telefon Raqam")
    
    # We can automatically link it to an existing User if found
    linked_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="Bog'langan Foydalanuvchi"
    )
    
    # Timestamp of when the request was made
    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Qayta tiklashga so'rov: {self.contact_input} ({self.requested_at.strftime('%Y-%m-%d %H:%M')})"

    class Meta:
        verbose_name = "Parolni Tiklash So'rovi"
        verbose_name_plural = "Parolni Tiklash So'rovlari"
