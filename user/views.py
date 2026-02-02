from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import UserProfile, PasswordResetRequest
from datetime import datetime,date

def calculate_age(dob):
    """Calculates age from a date of birth (datetime.date object)."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def index(request):
    if not request.user.is_authenticated:
        return redirect('courses:index') # Use the correct URL name
    
    # 1. Get the currently logged-in user and their profile
    user = request.user
    
    try:
        # Assuming the UserProfile object is guaranteed to exist due to the registration process
        user_profile = user.userprofile 
    except UserProfile.DoesNotExist:
        # Handle the edge case if a profile is missing (e.g., user created via shell)
        return redirect('user:login')
    
    # 2. Calculate Age and format date/gender
    age = None
    if user_profile and user_profile.date_of_birth:
        age = calculate_age(user_profile.date_of_birth)
        
    gender_display = user_profile.get_gender_display() if user_profile and user_profile.gender is not None else "Ma'lumot yo'q"

    # NOTE: You'll need a mechanism to count courses. For now, we'll use a placeholder.
    # If you have a 'Course' model, the real count might look like:
    # course_count = user_profile.enrolled_courses.count() 
    course_count = 4 # Placeholder for now
    
    # 3. Prepare the context dictionary
    context = {
        # Data from the built-in Django User model
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': f"{user.first_name} {user.last_name}",
        'email': user.email,
        
        # Data from the custom UserProfile model
        'profile': user_profile, # Pass the whole profile object
        'role': user_profile.get_role_display() if user_profile else "Noma'lum",
        'phone': user_profile.phone if user_profile else "Ma'lumot yo'q",
        'region': user_profile.region if user_profile else "Ma'lumot yo'q",
        'otm': user_profile.otm if user_profile else "Ma'lumot yo'q",
        
        # Calculated/Formatted Data
        'age': f"{age} yosh" if age is not None else "Ma'lumot yo'q",
        'gender_display': gender_display,
        'join_date': user.date_joined.strftime("%Y-%m-%d"), # Use the built-in User.date_joined
        'course_count': course_count,
    }

    return render(request, "user/profile.html", context)

def register_view(request):
    # ------------------------------------------------------------------
    # 1. CHECK IF USER IS ALREADY LOGGED IN
    if request.user.is_authenticated:
        # Redirect authenticated users to the index page (or profile page)
        messages.info(request, "Siz allaqachon tizimga kirgansiz.") # You are already logged in.
        return redirect('user:index') # Use the correct URL name
    # ------------------------------------------------------------------

    if request.method == 'POST':
        # 2. Retrieve data from the form
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        gender = request.POST.get('gender') # '1' for Male, '0' for Female
        region = request.POST.get('region')
        otm = request.POST.get('otm')
        date_of_birth_str = request.POST.get('date_of_birth')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        # 3. Basic Validation
        if password != password2:
            messages.error(request, "Parollar bir xil emas!")
            # Note: You might want to pass context data back to the template 
            # (like the entered form data) to avoid the user having to re-enter everything.
            return render(request, "user/register.html")

        # 4. Email existence check (using filter and exists is generally preferred)
        if User.objects.filter(email=email).exists():
            messages.error(request, "Bu email avval ro'yxatdan o'tgan.")
            return render(request, "user/register.html")
        
        # 5. Convert date of birth string to a Python date object
        date_of_birth = None
        if date_of_birth_str:
            try:
                date_of_birth = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Tug'ilgan sana noto'g'ri formatda kiritilgan.")
                return render(request, "user/register.html")

        # 6. Create the built-in Django User
        try:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )

            # 7. Create the linked UserProfile (Default role is 'student')
            UserProfile.objects.create(
                user=user,
                role='student',
                phone=phone_number,
                gender=int(gender) if gender in ['0', '1'] else None,
                region=region,
                otm=otm,
                date_of_birth=date_of_birth
            )

            # 8. Log the user in immediately after registration
            login(request, user)
            
            messages.success(request, "Muvaffaqiyatli ro'yxatdan o'tdingiz!")
            return redirect('user:index')

        except Exception as e:
            messages.error(request, f"Ro'yxatdan o'tishda xatolik yuz berdi: {e}")
            return render(request, "user/register.html")

    else: # If GET request, render the empty form
        return render(request, "user/register.html", {
            "profile": "profile",
        })
    

def login_view(request):
    # 1. Check if user is already logged in
    if request.user.is_authenticated:
        messages.info(request, "Siz allaqachon tizimga kirgansiz.")
        return redirect('user:index')

    if request.method == 'POST':
        # 2. Retrieve data from the form
        submitted_email = request.POST.get('email')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')
        
        username_to_authenticate = None
        user = None

        try:
            # FIX: Find the user by email (case-insensitive)
            user_by_email = User.objects.get(email__iexact=submitted_email)
            # Use the user's username (which is the email) for the authenticate function
            username_to_authenticate = user_by_email.username
            
            # 3. Authenticate using the retrieved username and submitted password
            user = authenticate(
                request, 
                username=username_to_authenticate, 
                password=password
            )
            
        except User.DoesNotExist:
            # If no user found with that email, 'user' remains None, which triggers the error message below
            redirect('user:index') 
        
        # 4. Check authentication result
        if user is not None:
            # Login successful
            login(request, user)
            
            if not remember_me:
                request.session.set_expiry(0) 
            
            messages.success(request, f"Xush kelibsiz, {user.first_name}!")
            return redirect('user:index')

        else:
            # Authentication failed (incorrect email/password combo or user not found)
            messages.error(request, "Email yoki parol noto'g'ri. Iltimos, tekshirib ko'ring.")
            return render(request, "user/login.html")

    else: # GET request
        return render(request, "user/login.html")
    
# ... (inside your existing views.py file)

def logout_view(request):
    # 1. Log the user out
    logout(request)
    
    # 2. Send a message
    messages.info(request, "Tizimdan muvaffaqiyatli chiqdingiz.")
    
    # 3. Redirect to the login page
    return redirect('user:login')

def forgot_password_view(request):
    if request.method == 'POST':
        # Get the input which could be email or phone number
        contact_input = request.POST.get('contact_input', '').strip()

        if not contact_input:
            messages.error(request, "Iltimos, email yoki telefon raqamingizni kiriting.")
            return render(request, "user/forgot_password.html")

        # Optional: Try to link the request to an existing user
        linked_user = None
        try:
            # Check by email or username (which is email)
            linked_user = User.objects.get(email__iexact=contact_input)
        except User.DoesNotExist:
            try:
                # Check if it's a phone number saved in UserProfile
                linked_user = User.objects.get(userprofile__phone=contact_input)
            except User.DoesNotExist:
                # User not found, but we still record the request
                pass

        # Save the request to the database
        PasswordResetRequest.objects.create(
            contact_input=contact_input,
            linked_user=linked_user
        )

        # Success Message
        messages.success(request, "Rahmat, so'rovingiz qabul qilindi. Administratorlarimiz tez orada parolingizni tiklab berishadi.")
        
        # Redirect back to the login page (or stay on the same page, but redirect is cleaner)
        return redirect('user:login')

    # GET request
    return render(request, "user/forgot_password.html")