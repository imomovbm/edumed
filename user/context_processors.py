def user_profile(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.userprofile
            return {
                'user_profile': profile,
                'unread_count': 0,  # later: Notification.objects.filter(user=request.user, read=False).count()
            }
        except:
            pass
    return {'user_profile': None, 'unread_count': 0}