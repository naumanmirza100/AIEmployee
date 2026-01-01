from rest_framework import serializers
from core.models import BlogPost, BlogTag, BlogPostTag
from django.contrib.auth.models import User


class BlogTagSerializer(serializers.ModelSerializer):
    """Serializer for Blog Tag"""
    
    class Meta:
        model = BlogTag
        fields = ['id', 'name', 'slug', 'created_at']
        read_only_fields = ['id', 'slug', 'created_at']


class BlogPostSerializer(serializers.ModelSerializer):
    """Serializer for Blog Post"""
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    author_email = serializers.EmailField(source='author.email', read_only=True)
    tags = serializers.SerializerMethodField()
    category = serializers.CharField(required=False)
    
    class Meta:
        model = BlogPost
        fields = ['id', 'slug', 'title', 'description', 'content', 'author', 'author_name', 
                  'author_email', 'category', 'featured_image', 'status', 'published_at', 
                  'views_count', 'tags', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'views_count', 'created_at', 'updated_at', 'published_at']
    
    def get_tags(self, obj):
        """Get tags for the blog post"""
        tags = obj.tags.all()
        return [{'id': tag.id, 'name': tag.name, 'slug': tag.slug} for tag in tags]


class BlogPostListSerializer(serializers.ModelSerializer):
    """Simplified serializer for blog post lists"""
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)
    tags = serializers.SerializerMethodField()
    
    class Meta:
        model = BlogPost
        fields = ['id', 'slug', 'title', 'description', 'author_name', 'category', 
                  'featured_image', 'status', 'published_at', 'views_count', 'tags', 'created_at']
    
    def get_tags(self, obj):
        """Get tags for the blog post"""
        tags = obj.tags.all()
        return [{'id': tag.id, 'name': tag.name, 'slug': tag.slug} for tag in tags]

