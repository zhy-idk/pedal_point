from django.db import models

# Create your models here.
class Product(models.Model):

    name = models.CharField(max_length=255, verbose_name="Product Name")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Price")
    category = models.CharField(max_length=255, verbose_name="Category")
    stock = models.IntegerField(verbose_name="Stock Quantity")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name="Product Image")
    slug = models.SlugField(max_length=255, unique=True, verbose_name="Slug")

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("_detail", kwargs={"pk": self.pk})
