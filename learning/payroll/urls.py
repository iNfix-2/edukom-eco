from django.urls import path
from . import views

app_name = 'payroll'

urlpatterns = [
    # Dashboard & Batch Calculations
    path('dashboard/', views.payroll_dashboard, name='dashboard'),
    path('upload/', views.upload_and_calculate_payroll, name='upload'),
    path('generate-lms/', views.generate_lms_payroll_view, name='generate_lms'),
    path('run/<uuid:run_id>/', views.payroll_run_detail, name='run_detail'),
    path('run/<uuid:run_id>/approve/', views.approve_payroll_run, name='approve_run'),
    path('run/<uuid:run_id>/export/excel/', views.export_payroll_excel_view, name='export_excel'),
    path('run/<uuid:run_id>/send-payslips/', views.send_all_payslips_view, name='send_payslips'),
    
    # Rates
    path('rates/', views.rate_matrix_view, name='rate_matrix'),

    # Tutor Bank Account KYC & Verification
    path('tutor/<int:tutor_id>/link-bank/', views.link_tutor_bank_account, name='link_bank'),
    path('tutor/payslip/<uuid:item_id>/', views.tutor_payslip_detail_view, name='tutor_payslip'),
    path('api/banks/', views.get_nigerian_banks_api, name='api_banks'),
    path('api/resolve-account/', views.resolve_nuban_api, name='api_resolve_account'),
    
    # Paystack Transfer Webhook
    path('webhook/paystack-transfer/', views.paystack_transfer_webhook_view, name='paystack_transfer_webhook'),
]
